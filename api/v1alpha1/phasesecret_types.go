package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
)

type PhaseSecretSpec struct {
	PhaseApp                string                   `json:"phaseApp,omitempty"`
	PhaseAppID              string                   `json:"phaseAppId,omitempty"`
	PhaseAppEnv             string                   `json:"phaseAppEnv,omitempty"`
	PhaseAppEnvPath         string                   `json:"phaseAppEnvPath,omitempty"`
	PhaseAppEnvTag          string                   `json:"phaseAppEnvTag,omitempty"`
	Authentication          *Authentication          `json:"authentication,omitempty"`
	PhaseHost               string                   `json:"phaseHost,omitempty"`
	ManagedSecretReferences []ManagedSecretReference `json:"managedSecretReferences,omitempty"`
	PollingInterval         int                      `json:"pollingInterval,omitempty"`
	RedeployLabelSelector   string                   `json:"redeployLabelSelector,omitempty"`
}

type Authentication struct {
	ServiceToken *ServiceTokenAuthentication `json:"serviceToken,omitempty"`
}

type ServiceTokenAuthentication struct {
	ServiceTokenSecretReference *ServiceTokenSecretReference `json:"serviceTokenSecretReference,omitempty"`
}

type ServiceTokenSecretReference struct {
	SecretName      string `json:"secretName,omitempty"`
	SecretNamespace string `json:"secretNamespace,omitempty"`
}

type ManagedSecretReference struct {
	SecretName      string               `json:"secretName,omitempty"`
	SecretNamespace string               `json:"secretNamespace,omitempty"`
	SecretType      string               `json:"secretType,omitempty"`
	NameTransformer string               `json:"nameTransformer,omitempty"`
	Processors      map[string]Processor `json:"processors,omitempty"`
	Template        *SecretTemplate      `json:"template,omitempty"`
}

type Processor struct {
	AsName          string `json:"asName,omitempty"`
	NameTransformer string `json:"nameTransformer,omitempty"`
	Type            string `json:"type,omitempty"`
}

type SecretTemplate struct {
	Metadata *SecretTemplateMetadata `json:"metadata,omitempty"`
}

type SecretTemplateMetadata struct {
	Labels      map[string]string `json:"labels,omitempty"`
	Annotations map[string]string `json:"annotations,omitempty"`
}

type PhaseSecretStatus struct {
	Conditions []metav1.Condition `json:"conditions,omitempty"`
}

type PhaseSecret struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   PhaseSecretSpec   `json:"spec,omitempty"`
	Status PhaseSecretStatus `json:"status,omitempty"`
}

func (in *PhaseSecret) DeepCopyObject() runtime.Object {
	if in == nil {
		return nil
	}
	out := new(PhaseSecret)
	in.DeepCopyInto(out)
	return out
}

func (in *PhaseSecret) DeepCopyInto(out *PhaseSecret) {
	*out = *in
	out.TypeMeta = in.TypeMeta
	in.ObjectMeta.DeepCopyInto(&out.ObjectMeta)
	in.Spec.DeepCopyInto(&out.Spec)
	in.Status.DeepCopyInto(&out.Status)
}

type PhaseSecretList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []PhaseSecret `json:"items"`
}

func (in *PhaseSecretList) DeepCopyObject() runtime.Object {
	if in == nil {
		return nil
	}
	out := new(PhaseSecretList)
	in.DeepCopyInto(out)
	return out
}

func (in *PhaseSecretList) DeepCopyInto(out *PhaseSecretList) {
	*out = *in
	out.TypeMeta = in.TypeMeta
	in.ListMeta.DeepCopyInto(&out.ListMeta)
	if in.Items != nil {
		out.Items = make([]PhaseSecret, len(in.Items))
		for i := range in.Items {
			in.Items[i].DeepCopyInto(&out.Items[i])
		}
	}
}

func (in *PhaseSecretSpec) DeepCopyInto(out *PhaseSecretSpec) {
	*out = *in
	if in.Authentication != nil {
		out.Authentication = new(Authentication)
		in.Authentication.DeepCopyInto(out.Authentication)
	}
	if in.ManagedSecretReferences != nil {
		out.ManagedSecretReferences = make([]ManagedSecretReference, len(in.ManagedSecretReferences))
		for i := range in.ManagedSecretReferences {
			in.ManagedSecretReferences[i].DeepCopyInto(&out.ManagedSecretReferences[i])
		}
	}
}

func (in *Authentication) DeepCopyInto(out *Authentication) {
	*out = *in
	if in.ServiceToken != nil {
		out.ServiceToken = new(ServiceTokenAuthentication)
		in.ServiceToken.DeepCopyInto(out.ServiceToken)
	}
}

func (in *ServiceTokenAuthentication) DeepCopyInto(out *ServiceTokenAuthentication) {
	*out = *in
	if in.ServiceTokenSecretReference != nil {
		ref := *in.ServiceTokenSecretReference
		out.ServiceTokenSecretReference = &ref
	}
}

func (in *ManagedSecretReference) DeepCopyInto(out *ManagedSecretReference) {
	*out = *in
	if in.Processors != nil {
		out.Processors = make(map[string]Processor, len(in.Processors))
		for key, value := range in.Processors {
			out.Processors[key] = value
		}
	}
	if in.Template != nil {
		out.Template = new(SecretTemplate)
		in.Template.DeepCopyInto(out.Template)
	}
}

func (in *SecretTemplate) DeepCopyInto(out *SecretTemplate) {
	*out = *in
	if in.Metadata != nil {
		out.Metadata = new(SecretTemplateMetadata)
		in.Metadata.DeepCopyInto(out.Metadata)
	}
}

func (in *SecretTemplateMetadata) DeepCopyInto(out *SecretTemplateMetadata) {
	*out = *in
	if in.Labels != nil {
		out.Labels = make(map[string]string, len(in.Labels))
		for key, value := range in.Labels {
			out.Labels[key] = value
		}
	}
	if in.Annotations != nil {
		out.Annotations = make(map[string]string, len(in.Annotations))
		for key, value := range in.Annotations {
			out.Annotations[key] = value
		}
	}
}

func (in *PhaseSecretStatus) DeepCopyInto(out *PhaseSecretStatus) {
	*out = *in
	if in.Conditions != nil {
		out.Conditions = make([]metav1.Condition, len(in.Conditions))
		copy(out.Conditions, in.Conditions)
	}
}
