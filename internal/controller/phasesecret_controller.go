package controller

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math/rand"
	"reflect"
	"regexp"
	"sort"
	"strings"
	"time"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/labels"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/tools/record"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	crcontroller "sigs.k8s.io/controller-runtime/pkg/controller"
	"sigs.k8s.io/controller-runtime/pkg/log"

	phasev1 "github.com/phasehq/kubernetes-secrets-operator/api/v1alpha1"
	phaseclient "github.com/phasehq/kubernetes-secrets-operator/internal/phase"
	"github.com/phasehq/kubernetes-secrets-operator/internal/syncstate"
	"github.com/phasehq/kubernetes-secrets-operator/internal/transform"
)

const (
	defaultPhaseHost           = "https://console.phase.dev"
	defaultPhaseAppEnv         = "production"
	defaultPhaseAppEnvPath     = "/"
	defaultPollingInterval     = 60 * time.Second
	minPollingInterval         = 5 * time.Second
	defaultServiceTokenName    = "phase-service-token"
	defaultSecretType          = corev1.SecretTypeOpaque
	defaultNameTransformer     = "upper_snake"
	redeployAnnotation         = "secrets.phase.dev/redeploy"
	redeployTimestamp          = "phase.autoredeploy.timestamp"
	serviceTokenSecretDataKey  = "token"
	onSecretReferenceErrorWarn = "Warn"
)

type PhaseClient interface {
	EnvironmentUpdatedAt(ctx context.Context, token, host, appName, appID, envName string) (time.Time, error)
	GetSecrets(ctx context.Context, token, host, appName, appID, envName, path, tag string, failOnReferenceError bool) (map[string]string, error)
}

type PhaseSecretReconciler struct {
	client.Client
	Scheme                  *runtime.Scheme
	Phase                   PhaseClient
	Cache                   *syncstate.Cache
	Recorder                record.EventRecorder
	JitterRatio             float64
	MaxConcurrentReconciles int
}

func NewPhaseSecretReconciler(k8sClient client.Client, scheme *runtime.Scheme) *PhaseSecretReconciler {
	return &PhaseSecretReconciler{
		Client:                  k8sClient,
		Scheme:                  scheme,
		Phase:                   phaseclient.NewFromEnv(),
		Cache:                   syncstate.New(""),
		JitterRatio:             0.10,
		MaxConcurrentReconciles: 10,
	}
}

func (r *PhaseSecretReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx).WithValues("phasesecret", req.NamespacedName.String())

	var ps phasev1.PhaseSecret
	if err := r.Get(ctx, req.NamespacedName, &ps); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	requeueAfter := r.requeueAfter(pollingInterval(ps.Spec.PollingInterval))
	result := ctrl.Result{RequeueAfter: requeueAfter}

	token, err := r.serviceToken(ctx, &ps)
	if err != nil {
		logger.Error(err, "failed to read service token secret")
		return result, nil
	}

	effective := effectiveSpec(&ps)
	updatedAt, err := r.Phase.EnvironmentUpdatedAt(ctx, token, effective.phaseHost, effective.phaseApp, effective.phaseAppID, effective.phaseAppEnv)
	if err != nil {
		logger.Error(err, "failed to fetch Phase environment metadata")
		return result, nil
	}

	specHash, err := hashSpec(ps.Spec)
	if err != nil {
		return result, err
	}

	needsSync, err := r.Cache.NeedsSync(ps.Namespace, ps.Name, string(ps.UID), updatedAt, specHash)
	if err != nil {
		logger.Error(err, "failed to read sync cache; syncing defensively")
		needsSync = true
	}
	if !needsSync {
		logger.V(1).Info("Phase environment and PhaseSecret spec unchanged; skipping full secret fetch")
		return result, nil
	}

	failOnReferenceError := !strings.EqualFold(ps.Spec.OnSecretReferenceError, onSecretReferenceErrorWarn)
	phaseSecrets, err := r.Phase.GetSecrets(ctx, token, effective.phaseHost, effective.phaseApp, effective.phaseAppID, effective.phaseAppEnv, effective.phaseAppEnvPath, effective.phaseAppEnvTag, failOnReferenceError)
	if err != nil {
		logger.Error(err, "failed to fetch Phase secrets")
		reason := "FetchFailed"
		if isReferenceResolutionError(err) {
			reason = "ReferenceResolutionFailed"
		}
		r.emitWarning(&ps, reason, err.Error())
		return result, nil
	}
	// In Warn mode the fetch succeeds even when references cannot be resolved,
	// leaving them as literal ${...} text. Surface that so the bypass is never silent.
	if !failOnReferenceError {
		if keys := unresolvedReferenceKeys(phaseSecrets); len(keys) > 0 {
			r.emitWarning(&ps, "UnresolvedReferences",
				fmt.Sprintf("%d Phase secret(s) contain references that could not be resolved and were synced as-is: %s", len(keys), strings.Join(keys, ", ")))
		}
	}

	changedSecretNames := make([]string, 0, len(ps.Spec.ManagedSecretReferences))
	var refErrs []error
	for _, ref := range ps.Spec.ManagedSecretReferences {
		secretName := ref.SecretName
		if secretName == "" {
			refErrs = append(refErrs, fmt.Errorf("managedSecretReferences entry has empty secretName"))
			r.emitWarning(&ps, "InvalidManagedSecretReference", "a managedSecretReferences entry has an empty secretName")
			continue
		}

		secretNamespace := ref.SecretNamespace
		if secretNamespace == "" {
			secretNamespace = ps.Namespace
		}
		secretType := corev1.SecretType(ref.SecretType)
		if secretType == "" {
			secretType = defaultSecretType
		}
		nameTransformer := ref.NameTransformer
		if nameTransformer == "" {
			nameTransformer = defaultNameTransformer
		}

		// A failure on one managed reference must not block the others. Collect the
		// error and continue; the checkpoint is held back below until every reference
		// has synced, so failed references are retried on the next poll.
		processed, err := transform.ProcessSecrets(phaseSecrets, ref.Processors, nameTransformer)
		if err != nil {
			logger.Error(err, "failed to process managed secret", "secret", types.NamespacedName{Name: secretName, Namespace: secretNamespace})
			r.emitWarning(&ps, "SecretProcessingFailed", fmt.Sprintf("%s/%s: %v", secretNamespace, secretName, err))
			refErrs = append(refErrs, err)
			continue
		}
		changed, err := r.upsertSecret(ctx, secretName, secretNamespace, secretType, processed, ref.Template)
		if err != nil {
			logger.Error(err, "failed to reconcile managed secret", "secret", types.NamespacedName{Name: secretName, Namespace: secretNamespace})
			r.emitWarning(&ps, "SecretSyncFailed", fmt.Sprintf("%s/%s: %v", secretNamespace, secretName, err))
			refErrs = append(refErrs, err)
			continue
		}
		if changed {
			changedSecretNames = append(changedSecretNames, secretName)
		}
	}

	// Only redeploy Deployments wired to secrets that actually changed this sync.
	if len(changedSecretNames) > 0 {
		if err := r.redeployAffectedDeployments(ctx, ps.Namespace, changedSecretNames, ps.Spec.RedeployLabelSelector); err != nil {
			logger.Error(err, "failed to patch one or more affected deployments")
		}
	}

	// Hold the sync checkpoint until every managed reference has synced, so the next
	// poll retries the failures instead of treating the environment as fully synced.
	if len(refErrs) > 0 {
		logger.Info("PhaseSecret sync completed with errors; checkpoint not advanced",
			"managedSecretCount", len(ps.Spec.ManagedSecretReferences), "failed", len(refErrs), "changed", len(changedSecretNames))
		return result, nil
	}

	if err := r.Cache.Update(ps.Namespace, ps.Name, string(ps.UID), updatedAt, specHash); err != nil {
		return result, err
	}

	logger.Info("PhaseSecret sync complete", "managedSecretCount", len(ps.Spec.ManagedSecretReferences), "changed", len(changedSecretNames), "nextSyncAfter", requeueAfter.String())
	return result, nil
}

func (r *PhaseSecretReconciler) emitWarning(ps *phasev1.PhaseSecret, reason, message string) {
	if r.Recorder != nil {
		r.Recorder.Event(ps, corev1.EventTypeWarning, reason, message)
	}
}

var referencePattern = regexp.MustCompile(`\$\{[^}]+\}`)

func isReferenceResolutionError(err error) bool {
	if err == nil {
		return false
	}
	msg := err.Error()
	return strings.Contains(msg, "resolve references") ||
		strings.Contains(msg, "could not be resolved") ||
		strings.Contains(msg, "referenced secrets")
}

func unresolvedReferenceKeys(secrets map[string]string) []string {
	keys := make([]string, 0)
	for key, value := range secrets {
		if referencePattern.MatchString(value) {
			keys = append(keys, key)
		}
	}
	sort.Strings(keys)
	return keys
}

func (r *PhaseSecretReconciler) serviceToken(ctx context.Context, ps *phasev1.PhaseSecret) (string, error) {
	name := defaultServiceTokenName
	namespace := ps.Namespace
	if ps.Spec.Authentication != nil &&
		ps.Spec.Authentication.ServiceToken != nil &&
		ps.Spec.Authentication.ServiceToken.ServiceTokenSecretReference != nil {
		ref := ps.Spec.Authentication.ServiceToken.ServiceTokenSecretReference
		if ref.SecretName != "" {
			name = ref.SecretName
		}
		if ref.SecretNamespace != "" {
			namespace = ref.SecretNamespace
		}
	}

	var secret corev1.Secret
	if err := r.Get(ctx, types.NamespacedName{Name: name, Namespace: namespace}, &secret); err != nil {
		return "", err
	}
	token, ok := secret.Data[serviceTokenSecretDataKey]
	if !ok {
		return "", fmt.Errorf("service token secret %s/%s is missing data key %q", namespace, name, serviceTokenSecretDataKey)
	}
	return string(token), nil
}

func (r *PhaseSecretReconciler) upsertSecret(ctx context.Context, name, namespace string, secretType corev1.SecretType, data map[string][]byte, tmpl *phasev1.SecretTemplate) (bool, error) {
	desiredLabels, desiredAnnotations := desiredMetadata(tmpl)

	var existing corev1.Secret
	err := r.Get(ctx, types.NamespacedName{Name: name, Namespace: namespace}, &existing)
	if apierrors.IsNotFound(err) {
		secret := &corev1.Secret{
			ObjectMeta: metav1.ObjectMeta{
				Name:        name,
				Namespace:   namespace,
				Labels:      desiredLabels,
				Annotations: desiredAnnotations,
			},
			Type: secretType,
			Data: data,
		}
		return true, r.Create(ctx, secret)
	}
	if err != nil {
		return false, err
	}

	updatedLabels := mergeMetadata(existing.Labels, desiredLabels)
	updatedAnnotations := mergeMetadata(existing.Annotations, desiredAnnotations)
	if existing.Type == secretType &&
		reflect.DeepEqual(existing.Data, data) &&
		reflect.DeepEqual(existing.Labels, updatedLabels) &&
		reflect.DeepEqual(existing.Annotations, updatedAnnotations) {
		return false, nil
	}

	updated := existing.DeepCopy()
	updated.Type = secretType
	updated.Data = data
	updated.Labels = updatedLabels
	updated.Annotations = updatedAnnotations

	if err := r.Update(ctx, updated); err != nil {
		return false, fmt.Errorf("atomic secret update failed: %w", err)
	}

	return true, nil
}

func (r *PhaseSecretReconciler) redeployAffectedDeployments(ctx context.Context, namespace string, affectedSecrets []string, labelSelector string) error {
	secretSet := map[string]struct{}{}
	for _, name := range affectedSecrets {
		secretSet[name] = struct{}{}
	}

	var opts []client.ListOption
	opts = append(opts, client.InNamespace(namespace))
	if labelSelector != "" {
		selector, err := labels.Parse(labelSelector)
		if err != nil {
			return err
		}
		opts = append(opts, client.MatchingLabelsSelector{Selector: selector})
	}

	var deployments appsv1.DeploymentList
	if err := r.List(ctx, &deployments, opts...); err != nil {
		return err
	}

	var firstErr error
	for i := range deployments.Items {
		deployment := &deployments.Items[i]
		if !shouldRedeploy(deployment, secretSet) {
			continue
		}

		original := deployment.DeepCopy()
		if deployment.Spec.Template.Annotations == nil {
			deployment.Spec.Template.Annotations = map[string]string{}
		}
		deployment.Spec.Template.Annotations[redeployTimestamp] = time.Now().UTC().Format(time.RFC3339Nano)
		if err := r.Patch(ctx, deployment, client.MergeFrom(original)); err != nil && firstErr == nil {
			firstErr = err
		}
	}
	return firstErr
}

func shouldRedeploy(deployment *appsv1.Deployment, affectedSecrets map[string]struct{}) bool {
	if deployment.Annotations == nil {
		return false
	}
	if _, ok := deployment.Annotations[redeployAnnotation]; !ok {
		return false
	}

	for _, container := range deployment.Spec.Template.Spec.Containers {
		for _, envFrom := range container.EnvFrom {
			if envFrom.SecretRef == nil {
				continue
			}
			if _, ok := affectedSecrets[envFrom.SecretRef.Name]; ok {
				return true
			}
		}
	}
	return false
}

func (r *PhaseSecretReconciler) SetupWithManager(mgr ctrl.Manager) error {
	maxConcurrent := r.MaxConcurrentReconciles
	if maxConcurrent <= 0 {
		maxConcurrent = 1
	}
	return ctrl.NewControllerManagedBy(mgr).
		For(&phasev1.PhaseSecret{}).
		WithOptions(crcontroller.Options{MaxConcurrentReconciles: maxConcurrent}).
		Complete(r)
}

func desiredMetadata(tmpl *phasev1.SecretTemplate) (map[string]string, map[string]string) {
	if tmpl == nil || tmpl.Metadata == nil {
		return nil, nil
	}
	labels := cloneMap(tmpl.Metadata.Labels)
	annotations := cloneMap(tmpl.Metadata.Annotations)
	return labels, annotations
}

func cloneMap(input map[string]string) map[string]string {
	if len(input) == 0 {
		return nil
	}
	output := make(map[string]string, len(input))
	for key, value := range input {
		output[key] = value
	}
	return output
}

func mergeMetadata(existing, desired map[string]string) map[string]string {
	merged := cloneMap(existing)
	if len(desired) == 0 {
		return merged
	}
	if merged == nil {
		merged = map[string]string{}
	}
	for key, value := range desired {
		merged[key] = value
	}
	return merged
}

type resolvedSpec struct {
	phaseHost       string
	phaseApp        string
	phaseAppID      string
	phaseAppEnv     string
	phaseAppEnvPath string
	phaseAppEnvTag  string
}

func effectiveSpec(ps *phasev1.PhaseSecret) resolvedSpec {
	spec := resolvedSpec{
		phaseHost:       ps.Spec.PhaseHost,
		phaseApp:        ps.Spec.PhaseApp,
		phaseAppID:      ps.Spec.PhaseAppID,
		phaseAppEnv:     ps.Spec.PhaseAppEnv,
		phaseAppEnvPath: ps.Spec.PhaseAppEnvPath,
		phaseAppEnvTag:  ps.Spec.PhaseAppEnvTag,
	}
	if spec.phaseHost == "" {
		spec.phaseHost = defaultPhaseHost
	}
	if spec.phaseAppEnv == "" {
		spec.phaseAppEnv = defaultPhaseAppEnv
	}
	if spec.phaseAppEnvPath == "" {
		spec.phaseAppEnvPath = defaultPhaseAppEnvPath
	}
	return spec
}

func pollingInterval(seconds int) time.Duration {
	if seconds <= 0 {
		return defaultPollingInterval
	}
	interval := time.Duration(seconds) * time.Second
	if interval < minPollingInterval {
		return minPollingInterval
	}
	return interval
}

func (r *PhaseSecretReconciler) requeueAfter(interval time.Duration) time.Duration {
	if r.JitterRatio <= 0 {
		return interval
	}
	maxJitter := int64(float64(interval) * r.JitterRatio)
	if maxJitter <= 0 {
		return interval
	}
	return interval + time.Duration(rand.Int63n(maxJitter+1))
}

func hashSpec(spec phasev1.PhaseSecretSpec) (string, error) {
	data, err := json.Marshal(spec)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:]), nil
}
