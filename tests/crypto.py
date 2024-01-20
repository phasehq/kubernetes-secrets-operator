import pytest
import base64
import re
import os
from src.utils.crypto import CryptoUtils
from nacl.secret import SecretBox

class TestCryptoUtils:
    def test_random_key_pair(self):
        # Testing if the generated key pair (public and private keys) are of the correct length (32 bytes each)
        public_key, private_key = CryptoUtils.random_key_pair()
        assert len(public_key) == 32
        assert len(private_key) == 32

    def test_client_session_keys(self):
        # Testing client session keys generation by ensuring the keys are of the correct length
        client_keypair = CryptoUtils.random_key_pair()
        server_keypair = CryptoUtils.random_key_pair()
        client_keys = CryptoUtils.client_session_keys(client_keypair, server_keypair[0])
        assert len(client_keys[0]) == 32 and len(client_keys[1]) == 32

    def test_server_session_keys(self):
        # Testing server session keys generation similar to client session keys
        client_keypair = CryptoUtils.random_key_pair()
        server_keypair = CryptoUtils.random_key_pair()
        server_keys = CryptoUtils.server_session_keys(server_keypair, client_keypair[0])
        assert len(server_keys[0]) == 32 and len(server_keys[1]) == 32

def test_encrypt_and_decrypt_asymmetric():
    # Testing asymmetric encryption and decryption to ensure the decrypted text matches the original plaintext
    test_plaintext = "Saigon, I'm still only in Saigon. Every time I think I'm gonna wake up back in the jungle.."
    public_key, private_key = CryptoUtils.random_key_pair()
    encrypted_data = CryptoUtils.encrypt_asymmetric(test_plaintext, public_key.hex())
    decrypted_data = CryptoUtils.decrypt_asymmetric(encrypted_data, private_key.hex(), public_key.hex())
    pattern = rf"ph:v{CryptoUtils.VERSION}:[0-9a-fA-F]{{64}}:.+"
    assert re.match(pattern, encrypted_data) is not None
    assert decrypted_data == test_plaintext

class TestBlake2bDigest:
    def test_blake2b_digest_length(self):
        # Testing the length of the BLAKE2b hash to ensure it's 64 characters (32 bytes hex encoded)
        input_str = "test string"
        salt = "salt"
        result = CryptoUtils.blake2b_digest(input_str, salt)
        assert len(result) == 64

    def test_blake2b_digest_consistency(self):
        # Testing hash consistency for the same input and salt
        input_str = "consistent input"
        salt = "consistent salt"
        hash1 = CryptoUtils.blake2b_digest(input_str, salt)
        hash2 = CryptoUtils.blake2b_digest(input_str, salt)
        assert hash1 == hash2

    def test_blake2b_digest_unique_with_different_inputs(self):
        # Ensuring different inputs with the same salt produce different hashes
        salt = "salt"
        hash1 = CryptoUtils.blake2b_digest("input1", salt)
        hash2 = CryptoUtils.blake2b_digest("input2", salt)
        assert hash1 != hash2

    def test_blake2b_digest_unique_with_different_salts(self):
        # Ensuring the same input with different salts produces different hashes
        input_str = "input"
        hash1 = CryptoUtils.blake2b_digest(input_str, "salt1")
        hash2 = CryptoUtils.blake2b_digest(input_str, "salt2")
        assert hash1 != hash2

    @pytest.mark.parametrize("input_str, salt, expected_hash", [
        # Testing known hash values for specific inputs and salts
        ("hello", "world", "38010cfe3a8e684cb17e6d049525e71d4e9dc3be173fc05bf5c5ca1c7e7c25e7"),
        ("another test", "another salt", "5afad949edcfb22bd24baeed4e75b0aeca41731b8dff78f989a5a4c0564f211f")
    ])
    def test_blake2b_digest_known_values(self, input_str, salt, expected_hash):
        # Testing that the calculated hash matches the expected known hash
        result = CryptoUtils.blake2b_digest(input_str, salt)
        assert result == expected_hash

class TestSecretSplitting:
    def test_xor_secret_splitting_and_reconstruction(self):
        # Testing XOR-based secret splitting and reconstruction
        original_secret_hex = "6eed8a70ac9e75ab1894b06d4a5e21d1072649529753f3244316c6d9e4c9c951"
        original_secret_bytes = bytes.fromhex(original_secret_hex)
        random_share = os.urandom(len(original_secret_bytes))
        second_share = CryptoUtils.xor_bytes(original_secret_bytes, random_share)
        reconstructed_secret_hex = CryptoUtils.reconstruct_secret([random_share.hex(), second_share.hex()])
        assert reconstructed_secret_hex == original_secret_hex
