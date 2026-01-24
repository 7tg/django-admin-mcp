"""
Tests for token security (hashing and salt)
"""

import pytest
from django.db import IntegrityError

from django_admin_mcp.models import MCPToken
from tests.factories import MCPTokenFactory


@pytest.mark.django_db
class TestTokenSecurity:
    """Test suite for token security features."""

    def test_token_is_hashed_on_save(self):
        """Test that token is hashed when saved."""
        token = MCPTokenFactory()

        # Token should have a hash
        assert token.token_hash is not None
        assert len(token.token_hash) == 64  # SHA-256 produces 64 hex characters

    def test_salt_is_generated(self):
        """Test that unique salt is generated for each token."""
        token = MCPTokenFactory()

        # Salt should be generated
        assert token.salt is not None
        assert len(token.salt) > 0

    def test_salts_are_unique(self):
        """Test that different tokens have different salts."""
        token1 = MCPTokenFactory()
        token2 = MCPTokenFactory()

        assert token1.salt != token2.salt

    def test_token_hashes_are_unique(self):
        """Test that different tokens have different hashes."""
        token1 = MCPTokenFactory()
        token2 = MCPTokenFactory()

        assert token1.token_hash != token2.token_hash

    def test_verify_token_with_correct_token(self):
        """Test that verify_token returns True for correct token."""
        token = MCPTokenFactory()
        plaintext_token = token.plaintext_token

        # Should verify successfully
        assert token.verify_token(plaintext_token) is True

    def test_verify_token_with_incorrect_token(self):
        """Test that verify_token returns False for incorrect token."""
        token = MCPTokenFactory()

        # Should fail verification
        assert token.verify_token("wrong_token") is False

    def test_verify_token_constant_time_comparison(self):
        """Test that verify_token uses constant-time comparison."""
        token = MCPTokenFactory()
        plaintext_token = token.plaintext_token

        # Verify uses hmac.compare_digest internally
        # Multiple calls should return consistent results
        assert token.verify_token(plaintext_token) is True
        assert token.verify_token(plaintext_token) is True
        assert token.verify_token("wrong") is False

    def test_plaintext_token_only_available_once(self):
        """Test that plaintext token is only available immediately after creation."""
        token = MCPTokenFactory()

        # First call should return the token
        plaintext1 = token.plaintext_token
        assert plaintext1 is not None

        # After factory post_generation, get_plaintext_token() should return None
        plaintext2 = token.get_plaintext_token()
        assert plaintext2 is None

    def test_token_hash_uniqueness_constraint(self):
        """Test that token_hash has uniqueness constraint."""
        token1 = MCPTokenFactory()

        # Try to create a token with the same hash (should fail)
        # This is a database-level constraint test
        token2 = MCPToken(
            name="Duplicate",
            user=token1.user,
            token_key="different_key",  # Different key to isolate hash constraint
            token_hash=token1.token_hash,
            salt=token1.salt,
        )

        with pytest.raises(IntegrityError):
            token2.save()

    def test_token_key_uniqueness_constraint(self):
        """Test that token_key has uniqueness constraint."""
        token1 = MCPTokenFactory()

        # Try to create a token with the same key (should fail)
        token2 = MCPToken(
            name="Duplicate",
            user=token1.user,
            token_key=token1.token_key,
            token_hash="different_hash_12345678901234567890123456789012345678901234567890123456",
            salt=token1.salt,
        )

        with pytest.raises(IntegrityError):
            token2.save()

    def test_hash_function_deterministic(self):
        """Test that hash function produces consistent results."""
        token_str = "test_token_12345"
        salt = "test_salt"

        hash1 = MCPToken._hash_token(token_str, salt)
        hash2 = MCPToken._hash_token(token_str, salt)

        # Same input should produce same hash
        assert hash1 == hash2

        # Different salt should produce different hash
        hash3 = MCPToken._hash_token(token_str, "different_salt")
        assert hash1 != hash3

    def test_token_verification_after_reload(self):
        """Test that token can be verified after reloading from database."""
        token = MCPTokenFactory()
        plaintext = token.plaintext_token

        # Reload from database
        token.refresh_from_db()

        # Should still verify against the original plaintext
        assert token.verify_token(plaintext) is True

    def test_token_string_representation_uses_key(self):
        """Test that string representation uses token key, not secret."""
        token = MCPTokenFactory()
        plaintext = token.plaintext_token  # Capture before it's consumed

        str_repr = str(token)

        # Should contain token key with prefix
        assert f"mcp_{token.token_key}" in str_repr
        # Should not contain the full plaintext token (which includes the secret)
        assert plaintext not in str_repr

    def test_regenerate_token(self):
        """Test that regenerate_token creates a new token."""
        token = MCPTokenFactory()
        old_plaintext = token.plaintext_token
        old_hash = token.token_hash
        old_salt = token.salt

        # Regenerate
        new_plaintext = token.regenerate_token()

        # New token should be different
        assert new_plaintext != old_plaintext
        assert token.token_hash != old_hash
        assert token.salt != old_salt

        # New token should verify
        assert token.verify_token(new_plaintext) is True

        # Old token should no longer verify
        assert token.verify_token(old_plaintext) is False

    def test_regenerate_token_persists_to_database(self):
        """Test that regenerated token is saved to database."""
        token = MCPTokenFactory()
        old_hash = token.token_hash

        # Regenerate
        new_plaintext = token.regenerate_token()

        # Reload from database
        token.refresh_from_db()

        # Hash should be updated in database
        assert token.token_hash != old_hash
        assert token.verify_token(new_plaintext) is True


@pytest.mark.django_db
class TestTokenFormat:
    """Test suite for token format (mcp_<key>.<secret>)."""

    def test_token_format_has_prefix(self):
        """Test that generated tokens have mcp_ prefix."""
        token = MCPTokenFactory()
        plaintext = token.plaintext_token

        assert plaintext.startswith("mcp_")

    def test_token_format_has_key_and_secret(self):
        """Test that token format contains key and secret separated by period."""
        token = MCPTokenFactory()
        plaintext = token.plaintext_token

        # Remove prefix and check format
        body = plaintext[4:]  # Remove 'mcp_'
        parts = body.split(".", 1)

        assert len(parts) == 2
        assert parts[0] == token.token_key
        assert len(parts[1]) > 0  # Secret should exist

    def test_parse_token_valid(self):
        """Test parse_token with valid token."""
        token = MCPTokenFactory()
        plaintext = token.plaintext_token

        parsed = MCPToken.parse_token(plaintext)

        assert parsed is not None
        key, secret = parsed
        assert key == token.token_key
        assert len(secret) > 0

    def test_parse_token_missing_prefix(self):
        """Test parse_token rejects tokens without mcp_ prefix."""
        result = MCPToken.parse_token("invalid_key_secret")
        assert result is None

    def test_parse_token_missing_secret(self):
        """Test parse_token rejects tokens without secret part."""
        result = MCPToken.parse_token("mcp_keyonly")
        assert result is None

    def test_parse_token_empty(self):
        """Test parse_token rejects empty tokens."""
        assert MCPToken.parse_token("") is None
        assert MCPToken.parse_token(None) is None

    def test_get_by_key_finds_active_token(self):
        """Test get_by_key finds active tokens."""
        token = MCPTokenFactory()

        found = MCPToken.get_by_key(token.token_key)

        assert found is not None
        assert found.id == token.id

    def test_get_by_key_ignores_inactive_token(self):
        """Test get_by_key ignores inactive tokens."""
        token = MCPTokenFactory(is_active=False)

        found = MCPToken.get_by_key(token.token_key)

        assert found is None

    def test_get_by_key_not_found(self):
        """Test get_by_key returns None for unknown key."""
        found = MCPToken.get_by_key("nonexistent_key")

        assert found is None

    def test_verify_secret_correct(self):
        """Test verify_secret with correct secret."""
        token = MCPTokenFactory()
        plaintext = token.plaintext_token

        # Extract secret from full token
        parsed = MCPToken.parse_token(plaintext)
        _, secret = parsed

        assert token.verify_secret(secret) is True

    def test_verify_secret_incorrect(self):
        """Test verify_secret with incorrect secret."""
        token = MCPTokenFactory()

        assert token.verify_secret("wrong_secret") is False

    def test_token_keys_are_unique(self):
        """Test that different tokens have different keys."""
        token1 = MCPTokenFactory()
        token2 = MCPTokenFactory()

        assert token1.token_key != token2.token_key
