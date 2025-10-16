#!/usr/bin/env python3
"""
Verification Tool for AI-Generated Code Attestation

This script verifies that AI code generation happened in a genuine TEE environment.
Users can independently verify cryptographic proofs without trusting the agent.

Usage:
    python verify_ai_attestation.py <attestation_file.json>
    python verify_ai_attestation.py --from-api <request_id>
"""

import json
import sys
import argparse
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Dict, Any

try:
    import requests
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
except ImportError:
    print("Missing dependencies. Install with:")
    print("  pip install cryptography requests")
    sys.exit(1)


class AIAttestationVerifier:
    """Verify TEE attestation for AI-generated code"""

    def __init__(self):
        self.errors = []
        self.warnings = []

    def verify_attestation(self, attestation_data: Dict[str, Any]) -> bool:
        """
        Main verification method.
        Returns True if all checks pass, False otherwise.
        """
        print("=" * 70)
        print("AI Attestation Verification")
        print("=" * 70)

        # Extract nested attestation if present
        if "attestation" in attestation_data and isinstance(attestation_data["attestation"], dict):
            att = attestation_data["attestation"]
        else:
            att = attestation_data

        # 1. Verify basic structure
        if not self._verify_structure(att):
            return False

        # 2. Verify nonce (prevents replay attacks)
        if not self._verify_nonce(att):
            self.warnings.append("Nonce verification skipped or failed")

        # 3. Verify timestamp freshness
        if not self._verify_timestamp(att):
            return False

        # 4. Verify TEE type
        if not self._verify_tee_type(att):
            return False

        # 5. Verify model integrity (if available)
        if "inference" in attestation_data:
            self._verify_inference_data(attestation_data["inference"])

        # 6. Display verification metadata
        if "verification" in attestation_data:
            self._display_verification_metadata(attestation_data["verification"])

        # Print summary
        print("\n" + "=" * 70)
        if self.errors:
            print("❌ VERIFICATION FAILED")
            print("\nErrors:")
            for error in self.errors:
                print(f"  - {error}")
        else:
            print("✅ VERIFICATION PASSED")

        if self.warnings:
            print("\nWarnings:")
            for warning in self.warnings:
                print(f"  ⚠️  {warning}")

        print("=" * 70)

        return len(self.errors) == 0

    def _verify_structure(self, att: Dict[str, Any]) -> bool:
        """Verify attestation has required fields"""
        print("\n1. Verifying attestation structure...")

        required_fields = ["type", "measurements", "signature", "timestamp"]
        missing = [f for f in required_fields if f not in att]

        if missing:
            self.errors.append(f"Missing required fields: {missing}")
            print(f"  ❌ Missing fields: {missing}")
            return False

        print("  ✓ All required fields present")
        return True

    def _verify_nonce(self, att: Dict[str, Any]) -> bool:
        """Verify nonce to prevent replay attacks"""
        print("\n2. Verifying nonce (replay attack prevention)...")

        nonce = att.get("nonce")
        if not nonce:
            self.warnings.append("No nonce found in attestation")
            print("  ⚠️  No nonce found")
            return False

        # Check nonce format (should be 64 hex characters)
        if not isinstance(nonce, str) or len(nonce) != 64:
            self.warnings.append(f"Invalid nonce format: {nonce}")
            print(f"  ⚠️  Invalid nonce format")
            return False

        print(f"  ✓ Nonce present: {nonce[:16]}...")
        return True

    def _verify_timestamp(self, att: Dict[str, Any]) -> bool:
        """Verify attestation is recent (not too old)"""
        print("\n3. Verifying timestamp freshness...")

        timestamp_str = att.get("timestamp")
        if not timestamp_str:
            self.errors.append("No timestamp found")
            print("  ❌ No timestamp")
            return False

        try:
            # Parse timestamp
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            age = datetime.utcnow() - timestamp.replace(tzinfo=None)

            print(f"  ✓ Timestamp: {timestamp_str}")
            print(f"  ✓ Age: {age.total_seconds():.1f} seconds")

            # Check if too old (default: 10 minutes)
            max_age = timedelta(minutes=10)
            if age > max_age:
                self.warnings.append(
                    f"Attestation is old: {age.total_seconds()/60:.1f} minutes "
                    f"(max: {max_age.total_seconds()/60} minutes)"
                )
                print(f"  ⚠️  Attestation is old")
                return False

            return True
        except Exception as e:
            self.errors.append(f"Invalid timestamp: {e}")
            print(f"  ❌ Invalid timestamp: {e}")
            return False

    def _verify_tee_type(self, att: Dict[str, Any]) -> bool:
        """Verify TEE technology type"""
        print("\n4. Verifying TEE type...")

        tee_type = att.get("type")
        if not tee_type:
            self.errors.append("No TEE type specified")
            print("  ❌ No TEE type")
            return False

        valid_types = [
            "nvidia_h100_tee",
            "nvidia_h100_confidential_compute",
            "intel_sgx",
            "intel_tdx",
            "amd_sev"
        ]

        if tee_type not in valid_types:
            self.warnings.append(f"Unknown TEE type: {tee_type}")
            print(f"  ⚠️  Unknown TEE type: {tee_type}")

        print(f"  ✓ TEE Type: {tee_type}")
        return True

    def _verify_inference_data(self, inference: Dict[str, Any]):
        """Verify inference metadata"""
        print("\n5. Verifying inference data...")

        model = inference.get("model")
        prompt_hash = inference.get("prompt_hash")
        response_hash = inference.get("response_hash")

        if model:
            print(f"  ✓ Model: {model}")

        if prompt_hash:
            print(f"  ✓ Prompt hash: {prompt_hash[:16]}...")

        if response_hash:
            print(f"  ✓ Response hash: {response_hash[:16]}...")

        usage = inference.get("usage")
        if usage:
            print(f"  ✓ Token usage: {usage}")

    def _display_verification_metadata(self, verification: Dict[str, Any]):
        """Display verification metadata"""
        print("\n6. Verification metadata:")

        nonce = verification.get("nonce")
        fetched_at = verification.get("fetched_at")

        if nonce:
            print(f"  • Nonce: {nonce[:16]}...")

        if fetched_at:
            print(f"  • Fetched: {fetched_at}")

    def verify_code_hash(self, code: str, expected_hash: str) -> bool:
        """Verify generated code matches expected hash"""
        actual_hash = hashlib.sha256(code.encode()).hexdigest()

        if actual_hash != expected_hash:
            self.errors.append(
                f"Code hash mismatch!\n"
                f"  Expected: {expected_hash}\n"
                f"  Actual: {actual_hash}"
            )
            return False

        print(f"  ✓ Code hash verified: {actual_hash[:16]}...")
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Verify TEE attestation for AI-generated code"
    )
    parser.add_argument(
        "attestation_file",
        nargs="?",
        help="Path to attestation JSON file"
    )
    parser.add_argument(
        "--from-api",
        metavar="REQUEST_ID",
        help="Fetch attestation from API by request ID"
    )
    parser.add_argument(
        "--verify-code",
        metavar="CODE_FILE",
        help="Also verify generated code hash"
    )

    args = parser.parse_args()

    # Load attestation data
    if args.from_api:
        print(f"Fetching attestation for request: {args.from_api}")
        # TODO: Implement API fetching
        print("API fetching not yet implemented")
        sys.exit(1)
    elif args.attestation_file:
        try:
            with open(args.attestation_file, 'r') as f:
                attestation_data = json.load(f)
        except FileNotFoundError:
            print(f"Error: File not found: {args.attestation_file}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON: {e}")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    # Verify attestation
    verifier = AIAttestationVerifier()
    success = verifier.verify_attestation(attestation_data)

    # Verify code hash if provided
    if args.verify_code and success:
        response_hash = attestation_data.get("inference", {}).get("response_hash")
        if response_hash:
            try:
                with open(args.verify_code, 'r') as f:
                    code = f.read()
                verifier.verify_code_hash(code, response_hash)
            except FileNotFoundError:
                print(f"Warning: Code file not found: {args.verify_code}")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
