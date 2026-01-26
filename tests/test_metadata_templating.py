"""Unit tests for metadata templating feature.

Tests the merge_secret_metadata() and metadata_has_changed() functions
to ensure proper CNCF-compliant metadata handling.
"""

import pytest
import sys
import os
from unittest.mock import Mock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from main import merge_secret_metadata, metadata_has_changed
import kubernetes.client


class TestMergeSecretMetadata:
    """Test suite for merge_secret_metadata() function."""
    
    def test_basic_label_merging(self):
        """Test that user-defined labels are merged with operator labels."""
        secret_ref = {
            'secretName': 'test-secret',
            'template': {
                'metadata': {
                    'labels': {
                        'environment': 'production',
                        'team': 'platform'
                    }
                }
            }
        }
        
        logger = Mock()
        labels, annotations = merge_secret_metadata(
            secret_ref, 'test-secret', 'default', 'test-phasesecret', logger
        )
        
        # User labels should be present
        assert labels['environment'] == 'production'
        assert labels['team'] == 'platform'
        
        # Operator-managed labels should be present
        assert labels['app.kubernetes.io/managed-by'] == 'phase-secrets-operator'
        assert labels['secrets.phase.dev/phasesecret'] == 'test-phasesecret'
        assert labels['secrets.phase.dev/managed'] == 'true'
        
        # KEP-1623 recommended labels
        assert labels['app.kubernetes.io/name'] == 'phase-secret'
        assert labels['app.kubernetes.io/instance'] == 'test-secret'
        assert labels['app.kubernetes.io/component'] == 'secret'
    
    def test_basic_annotation_merging(self):
        """Test that user-defined annotations are merged."""
        secret_ref = {
            'template': {
                'metadata': {
                    'annotations': {
                        'contact': 'team@example.com',
                        'description': 'Test secret'
                    }
                }
            }
        }
        
        logger = Mock()
        labels, annotations = merge_secret_metadata(
            secret_ref, 'test-secret', 'default', 'test-cr', logger
        )
        
        # User annotations should be present
        assert annotations['contact'] == 'team@example.com'
        assert annotations['description'] == 'Test secret'
        
        # Operator annotation should be present
        assert 'secrets.phase.dev/last-sync' in annotations
        assert annotations['secrets.phase.dev/last-sync'].endswith('Z')
    
    def test_reserved_namespace_protection(self):
        """Test that reserved namespace labels are rejected."""
        secret_ref = {
            'template': {
                'metadata': {
                    'labels': {
                        'secrets.phase.dev/custom': 'should-be-rejected',
                        'secrets.phase.dev/phasesecret': 'fake-owner',
                        'safe-label': 'should-work'
                    }
                }
            }
        }
        
        logger = Mock()
        labels, annotations = merge_secret_metadata(
            secret_ref, 'test-secret', 'default', 'real-owner', logger
        )
        
        # Reserved labels should be rejected
        assert labels.get('secrets.phase.dev/custom') is None
        
        # Operator-managed label should have correct value, not user-provided
        assert labels['secrets.phase.dev/phasesecret'] == 'real-owner'
        
        # Safe label should be present
        assert labels['safe-label'] == 'should-work'
        
        # Should have logged warnings
        assert logger.warning.call_count >= 1
    
    def test_protected_labels_cannot_override(self):
        """Test that operator-managed labels cannot be overridden."""
        secret_ref = {
            'template': {
                'metadata': {
                    'labels': {
                        'app.kubernetes.io/managed-by': 'fake-operator',
                        'app.kubernetes.io/name': 'fake-name',
                        'custom-label': 'ok'
                    }
                }
            }
        }
        
        logger = Mock()
        labels, annotations = merge_secret_metadata(
            secret_ref, 'test-secret', 'default', 'test-cr', logger
        )
        
        # Protected labels should maintain operator values
        assert labels['app.kubernetes.io/managed-by'] == 'phase-secrets-operator'
        assert labels['app.kubernetes.io/name'] == 'phase-secret'
        
        # Custom label should work
        assert labels['custom-label'] == 'ok'
        
        # Should have logged warnings
        assert logger.warning.call_count >= 1
    
    def test_empty_template(self):
        """Test handling of secret reference without template."""
        secret_ref = {
            'secretName': 'test-secret'
            # No template field
        }
        
        logger = Mock()
        labels, annotations = merge_secret_metadata(
            secret_ref, 'test-secret', 'default', 'test-cr', logger
        )
        
        # Should only have operator-managed labels
        assert labels['app.kubernetes.io/managed-by'] == 'phase-secrets-operator'
        assert labels['secrets.phase.dev/phasesecret'] == 'test-cr'
        
        # Should not have user labels
        assert len([k for k in labels.keys() if not k.startswith('app.kubernetes.io') 
                    and not k.startswith('secrets.phase.dev')]) == 0
    
    def test_argocd_integration(self):
        """Test ArgoCD cluster secret label application."""
        secret_ref = {
            'template': {
                'metadata': {
                    'labels': {
                        'argocd.argoproj.io/secret-type': 'cluster'
                    }
                }
            }
        }
        
        logger = Mock()
        labels, annotations = merge_secret_metadata(
            secret_ref, 'cluster-secret', 'argocd', 'argocd-clusters', logger
        )
        
        # ArgoCD label should be present
        assert labels['argocd.argoproj.io/secret-type'] == 'cluster'
        
        # Operator labels should also be present
        assert labels['app.kubernetes.io/managed-by'] == 'phase-secrets-operator'
    
    def test_cert_manager_integration(self):
        """Test Cert-Manager certificate labels."""
        secret_ref = {
            'template': {
                'metadata': {
                    'labels': {
                        'cert-manager.io/certificate-name': 'example-com',
                        'cert-manager.io/common-name': 'example.com'
                    },
                    'annotations': {
                        'cert-manager.io/alt-names': '*.example.com,example.com'
                    }
                }
            }
        }
        
        logger = Mock()
        labels, annotations = merge_secret_metadata(
            secret_ref, 'tls-cert', 'default', 'tls-secrets', logger
        )
        
        # Cert-Manager labels should be present
        assert labels['cert-manager.io/certificate-name'] == 'example-com'
        assert labels['cert-manager.io/common-name'] == 'example.com'
        
        # Cert-Manager annotations should be present
        assert annotations['cert-manager.io/alt-names'] == '*.example.com,example.com'
    
    def test_value_type_conversion(self):
        """Test that non-string values are converted to strings."""
        secret_ref = {
            'template': {
                'metadata': {
                    'labels': {
                        'numeric': 123,
                        'boolean': True
                    },
                    'annotations': {
                        'port': 8080
                    }
                }
            }
        }
        
        logger = Mock()
        labels, annotations = merge_secret_metadata(
            secret_ref, 'test', 'default', 'test', logger
        )
        
        # Values should be converted to strings
        assert labels['numeric'] == '123'
        assert labels['boolean'] == 'True'
        assert annotations['port'] == '8080'


class TestMetadataHasChanged:
    """Test suite for metadata_has_changed() function."""
    
    def test_no_changes(self):
        """Test that unchanged metadata returns False."""
        existing_secret = kubernetes.client.V1Secret(
            metadata=kubernetes.client.V1ObjectMeta(
                labels={'key': 'value'},
                annotations={'note': 'test'}
            )
        )
        
        expected_labels = {'key': 'value'}
        expected_annotations = {'note': 'test'}
        
        assert metadata_has_changed(existing_secret, expected_labels, expected_annotations) is False
    
    def test_label_changed(self):
        """Test that changed labels are detected."""
        existing_secret = kubernetes.client.V1Secret(
            metadata=kubernetes.client.V1ObjectMeta(
                labels={'key': 'old-value'},
                annotations={'note': 'test'}
            )
        )
        
        expected_labels = {'key': 'new-value'}
        expected_annotations = {'note': 'test'}
        
        assert metadata_has_changed(existing_secret, expected_labels, expected_annotations) is True
    
    def test_annotation_changed(self):
        """Test that changed annotations are detected."""
        existing_secret = kubernetes.client.V1Secret(
            metadata=kubernetes.client.V1ObjectMeta(
                labels={'key': 'value'},
                annotations={'note': 'old'}
            )
        )
        
        expected_labels = {'key': 'value'}
        expected_annotations = {'note': 'new'}
        
        assert metadata_has_changed(existing_secret, expected_labels, expected_annotations) is True
    
    def test_added_label(self):
        """Test that added labels are detected."""
        existing_secret = kubernetes.client.V1Secret(
            metadata=kubernetes.client.V1ObjectMeta(
                labels={'key1': 'value1'},
                annotations={}
            )
        )
        
        expected_labels = {'key1': 'value1', 'key2': 'value2'}
        expected_annotations = {}
        
        assert metadata_has_changed(existing_secret, expected_labels, expected_annotations) is True
    
    def test_removed_label(self):
        """Test that removed labels are detected."""
        existing_secret = kubernetes.client.V1Secret(
            metadata=kubernetes.client.V1ObjectMeta(
                labels={'key1': 'value1', 'key2': 'value2'},
                annotations={}
            )
        )
        
        expected_labels = {'key1': 'value1'}
        expected_annotations = {}
        
        assert metadata_has_changed(existing_secret, expected_labels, expected_annotations) is True
    
    def test_none_metadata(self):
        """Test handling of None metadata."""
        existing_secret = kubernetes.client.V1Secret(
            metadata=kubernetes.client.V1ObjectMeta(
                labels=None,
                annotations=None
            )
        )
        
        expected_labels = {'key': 'value'}
        expected_annotations = {'note': 'test'}
        
        assert metadata_has_changed(existing_secret, expected_labels, expected_annotations) is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])