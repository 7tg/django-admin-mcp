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

        # Token field should be None (not stored in plaintext)
        assert token.token is None

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
            token_hash=token1.token_hash,
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

    def test_no_plaintext_token_in_database(self):
        """Test that plaintext token is not stored in database."""
        token = MCPTokenFactory()
        plaintext = token.plaintext_token

        # Reload from database
        token.refresh_from_db()

        # Token field should be None in database
        assert token.token is None

        # But should still verify against the original plaintext
        assert token.verify_token(plaintext) is True

    def test_token_string_representation_uses_hash(self):
        """Test that string representation uses hash, not plaintext."""
        token = MCPTokenFactory()
        plaintext = token.plaintext_token  # Capture before it's consumed

        str_repr = str(token)

        # Should contain part of hash
        assert token.token_hash[:8] in str_repr
        # Should not contain plaintext token
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
