package controller

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	phasev1 "github.com/phasehq/kubernetes-secrets-operator/api/v1alpha1"
	"github.com/phasehq/kubernetes-secrets-operator/internal/syncstate"
)

type fakePhaseClient struct {
	updatedAt time.Time
	secrets   map[string]string
	metaCalls int
	getCalls  int
}

func (f *fakePhaseClient) EnvironmentUpdatedAt(context.Context, string, string, string, string, string) (time.Time, error) {
	f.metaCalls++
	return f.updatedAt, nil
}

func (f *fakePhaseClient) GetSecrets(context.Context, string, string, string, string, string, string, string) (map[string]string, error) {
	f.getCalls++
	return f.secrets, nil
}

func TestReconcileCreatesSecretRedeploysAndSkipsUnchanged(t *testing.T) {
	ctx := context.Background()
	scheme := testScheme(t)
	ps := testPhaseSecret()
	phase := &fakePhaseClient{
		updatedAt: time.Date(2026, 6, 14, 12, 0, 0, 0, time.UTC),
		secrets:   map[string]string{"API_KEY": "secret"},
	}

	k8sClient := fake.NewClientBuilder().
		WithScheme(scheme).
		WithObjects(&ps, tokenSecret("app-a", "phase-service-token"), deployment("app-a", "web", "managed", map[string]string{"tier": "api"})).
		Build()
	reconciler := testReconciler(k8sClient, scheme, phase, t.TempDir())

	result, err := reconciler.Reconcile(ctx, requestFor(ps))
	if err != nil {
		t.Fatalf("Reconcile() error = %v", err)
	}
	if result.RequeueAfter != defaultPollingInterval {
		t.Fatalf("RequeueAfter = %s, want %s", result.RequeueAfter, defaultPollingInterval)
	}

	var secret corev1.Secret
	if err := k8sClient.Get(ctx, types.NamespacedName{Name: "managed", Namespace: "secrets-a"}, &secret); err != nil {
		t.Fatalf("managed secret was not created: %v", err)
	}
	if string(secret.Data["API_KEY"]) != "secret" {
		t.Fatalf("secret data = %q, want %q", string(secret.Data["API_KEY"]), "secret")
	}

	var patched appsv1.Deployment
	if err := k8sClient.Get(ctx, types.NamespacedName{Name: "web", Namespace: "app-a"}, &patched); err != nil {
		t.Fatalf("deployment get error = %v", err)
	}
	if patched.Spec.Template.Annotations[redeployTimestamp] == "" {
		t.Fatal("deployment was not patched for redeploy")
	}

	if phase.metaCalls != 1 || phase.getCalls != 1 {
		t.Fatalf("phase calls after first reconcile = meta:%d get:%d, want 1/1", phase.metaCalls, phase.getCalls)
	}

	if _, err := reconciler.Reconcile(ctx, requestFor(ps)); err != nil {
		t.Fatalf("second Reconcile() error = %v", err)
	}
	if phase.metaCalls != 2 || phase.getCalls != 1 {
		t.Fatalf("unchanged reconcile should skip full fetch; got meta:%d get:%d", phase.metaCalls, phase.getCalls)
	}
}

func TestSpecChangeForcesSyncAndMetadataOnlyUpdate(t *testing.T) {
	ctx := context.Background()
	scheme := testScheme(t)
	ps := testPhaseSecret()
	phase := &fakePhaseClient{
		updatedAt: time.Date(2026, 6, 14, 12, 0, 0, 0, time.UTC),
		secrets:   map[string]string{"API_KEY": "secret"},
	}

	k8sClient := fake.NewClientBuilder().
		WithScheme(scheme).
		WithObjects(&ps, tokenSecret("app-a", "phase-service-token")).
		Build()
	reconciler := testReconciler(k8sClient, scheme, phase, t.TempDir())

	if _, err := reconciler.Reconcile(ctx, requestFor(ps)); err != nil {
		t.Fatalf("first Reconcile() error = %v", err)
	}

	var updated phasev1.PhaseSecret
	if err := k8sClient.Get(ctx, types.NamespacedName{Name: ps.Name, Namespace: ps.Namespace}, &updated); err != nil {
		t.Fatalf("PhaseSecret get error = %v", err)
	}
	updated.Spec.ManagedSecretReferences[0].Template = &phasev1.SecretTemplate{
		Metadata: &phasev1.SecretTemplateMetadata{
			Labels: map[string]string{"argocd.argoproj.io/secret-type": "cluster"},
		},
	}
	if err := k8sClient.Update(ctx, &updated); err != nil {
		t.Fatalf("PhaseSecret update error = %v", err)
	}

	if _, err := reconciler.Reconcile(ctx, requestFor(ps)); err != nil {
		t.Fatalf("second Reconcile() error = %v", err)
	}
	if phase.getCalls != 2 {
		t.Fatalf("spec change should force full fetch; got %d full fetches", phase.getCalls)
	}

	var secret corev1.Secret
	if err := k8sClient.Get(ctx, types.NamespacedName{Name: "managed", Namespace: "secrets-a"}, &secret); err != nil {
		t.Fatalf("managed secret get error = %v", err)
	}
	if secret.Labels["argocd.argoproj.io/secret-type"] != "cluster" {
		t.Fatalf("metadata-only update did not apply labels: %#v", secret.Labels)
	}
}

func TestRedeployLabelSelectorNarrowsDeploymentScan(t *testing.T) {
	ctx := context.Background()
	scheme := testScheme(t)
	ps := testPhaseSecret()
	ps.Spec.RedeployLabelSelector = "tier=api"
	phase := &fakePhaseClient{
		updatedAt: time.Date(2026, 6, 14, 12, 0, 0, 0, time.UTC),
		secrets:   map[string]string{"API_KEY": "secret"},
	}

	selected := deployment("app-a", "selected", "managed", map[string]string{"tier": "api"})
	skipped := deployment("app-a", "skipped", "managed", map[string]string{"tier": "worker"})
	k8sClient := fake.NewClientBuilder().
		WithScheme(scheme).
		WithObjects(&ps, tokenSecret("app-a", "phase-service-token"), selected, skipped).
		Build()
	reconciler := testReconciler(k8sClient, scheme, phase, t.TempDir())

	if _, err := reconciler.Reconcile(ctx, requestFor(ps)); err != nil {
		t.Fatalf("Reconcile() error = %v", err)
	}

	var gotSelected appsv1.Deployment
	if err := k8sClient.Get(ctx, types.NamespacedName{Name: "selected", Namespace: "app-a"}, &gotSelected); err != nil {
		t.Fatalf("selected deployment get error = %v", err)
	}
	if gotSelected.Spec.Template.Annotations[redeployTimestamp] == "" {
		t.Fatal("selected deployment was not patched")
	}

	var gotSkipped appsv1.Deployment
	if err := k8sClient.Get(ctx, types.NamespacedName{Name: "skipped", Namespace: "app-a"}, &gotSkipped); err != nil {
		t.Fatalf("skipped deployment get error = %v", err)
	}
	if gotSkipped.Spec.Template.Annotations[redeployTimestamp] != "" {
		t.Fatal("deployment outside redeployLabelSelector was patched")
	}
}

func testScheme(t *testing.T) *runtime.Scheme {
	t.Helper()
	scheme := runtime.NewScheme()
	if err := clientgoscheme.AddToScheme(scheme); err != nil {
		t.Fatalf("client-go scheme error = %v", err)
	}
	if err := phasev1.AddToScheme(scheme); err != nil {
		t.Fatalf("phase scheme error = %v", err)
	}
	return scheme
}

func testReconciler(k8sClient client.Client, scheme *runtime.Scheme, phase *fakePhaseClient, dir string) *PhaseSecretReconciler {
	return &PhaseSecretReconciler{
		Client:      k8sClient,
		Scheme:      scheme,
		Phase:       phase,
		Cache:       syncstate.New(filepath.Join(dir, "cache.json")),
		JitterRatio: 0,
	}
}

func testPhaseSecret() phasev1.PhaseSecret {
	return phasev1.PhaseSecret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "example",
			Namespace: "app-a",
			UID:       types.UID("uid"),
		},
		Spec: phasev1.PhaseSecretSpec{
			PhaseApp:    "test",
			PhaseAppEnv: "development",
			ManagedSecretReferences: []phasev1.ManagedSecretReference{
				{
					SecretName:      "managed",
					SecretNamespace: "secrets-a",
					SecretType:      string(corev1.SecretTypeOpaque),
				},
			},
		},
	}
}

func tokenSecret(namespace, name string) *corev1.Secret {
	return &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: namespace},
		Data:       map[string][]byte{"token": []byte("pss_service:v2:test")},
	}
}

func deployment(namespace, name, secretName string, deploymentLabels map[string]string) *appsv1.Deployment {
	return &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name:        name,
			Namespace:   namespace,
			Labels:      deploymentLabels,
			Annotations: map[string]string{redeployAnnotation: "true"},
		},
		Spec: appsv1.DeploymentSpec{
			Template: corev1.PodTemplateSpec{
				Spec: corev1.PodSpec{
					Containers: []corev1.Container{
						{
							Name: "app",
							EnvFrom: []corev1.EnvFromSource{
								{SecretRef: &corev1.SecretEnvSource{LocalObjectReference: corev1.LocalObjectReference{Name: secretName}}},
							},
						},
					},
				},
			},
		},
	}
}

func requestFor(ps phasev1.PhaseSecret) ctrl.Request {
	return ctrl.Request{NamespacedName: types.NamespacedName{Name: ps.Name, Namespace: ps.Namespace}}
}
