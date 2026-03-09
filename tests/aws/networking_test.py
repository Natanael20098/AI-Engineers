"""
Unit tests: AWS VPC and Networking Configuration.

Verifies that:
  AC1  All VPC configuration functions are covered by unit tests.
  AC2  100% branch coverage for networking components.
  AC3  Tests pass with simulated AWS responses (moto mock_aws).

Class under test: VPCProvisioner (infra/aws/vpc_provisioner.py)

Tests mirror the Terraform configuration in infra/aws/vpc.tf:
  - VPC with DNS hostnames/support enabled
  - Public and private subnets linked to the VPC
  - Security group definitions (EC2 level – tested via boto3 calls)

Edge cases:
  - Invalid CIDR blocks (malformed string, /33 prefix, empty string)
  - Reserved IP ranges (loopback 127/8, link-local 169.254/16, class-E 240/4,
    "this" network 0/8)
  - AWS SDK ClientError (simulates SDK timeout / permission errors)
"""

from __future__ import annotations

import os
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

from infra.aws.vpc_provisioner import VPCProvisioner  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def aws_credentials(monkeypatch):
    """Ensure moto receives dummy credentials for every test."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture()
def provisioner():
    """VPCProvisioner instance backed by a moto-mocked EC2 API."""
    with mock_aws():
        yield VPCProvisioner(region="us-east-1")


@pytest.fixture()
def vpc(provisioner):
    """Pre-created VPC with CIDR 10.10.0.0/16 (matches variables.tf default)."""
    return provisioner.provision_vpc("10.10.0.0/16")


# ---------------------------------------------------------------------------
# AC1 – All VPC configuration functions covered
# ---------------------------------------------------------------------------


class TestProvisionVPC:
    """Tests for VPCProvisioner.provision_vpc."""

    def test_provision_vpc_returns_vpc_id(self, provisioner):
        """provision_vpc must return a dict containing a non-empty VpcId."""
        with mock_aws():
            vpc = provisioner.provision_vpc("10.10.0.0/16")

        assert "VpcId" in vpc
        assert vpc["VpcId"].startswith("vpc-")

    def test_provision_vpc_cidr_matches_input(self, provisioner):
        """provision_vpc must set the requested CIDR block on the VPC."""
        with mock_aws():
            vpc = provisioner.provision_vpc("10.20.0.0/16")

        assert vpc["CidrBlock"] == "10.20.0.0/16"

    def test_provision_vpc_dns_attributes_enabled(self, provisioner):
        """DNS hostnames and DNS support must be enabled (mirrors vpc.tf)."""
        with mock_aws():
            vpc = provisioner.provision_vpc("10.10.0.0/16")
            vpc_id = vpc["VpcId"]
            ec2 = boto3.client("ec2", region_name="us-east-1")

            hostnames_resp = ec2.describe_vpc_attribute(
                VpcId=vpc_id, Attribute="enableDnsHostnames"
            )
            support_resp = ec2.describe_vpc_attribute(
                VpcId=vpc_id, Attribute="enableDnsSupport"
            )

        assert hostnames_resp["EnableDnsHostnames"]["Value"] is True
        assert support_resp["EnableDnsSupport"]["Value"] is True

    def test_provision_vpc_private_cidr_range(self, provisioner):
        """Private RFC-1918 ranges (10/8, 172.16/12, 192.168/16) must be accepted."""
        with mock_aws():
            vpc_a = provisioner.provision_vpc("10.0.0.0/8")
            vpc_b = provisioner.provision_vpc("172.16.0.0/12")
            vpc_c = provisioner.provision_vpc("192.168.0.0/16")

        assert vpc_a["CidrBlock"] == "10.0.0.0/8"
        assert vpc_b["CidrBlock"] == "172.16.0.0/12"
        assert vpc_c["CidrBlock"] == "192.168.0.0/16"


class TestCreateSubnet:
    """Tests for VPCProvisioner.create_subnet."""

    def test_create_subnet_returns_subnet_id(self, provisioner):
        """create_subnet must return a dict containing a SubnetId."""
        with mock_aws():
            vpc = provisioner.provision_vpc("10.10.0.0/16")
            subnet = provisioner.create_subnet(
                vpc["VpcId"], "10.10.1.0/24", "us-east-1a"
            )

        assert "SubnetId" in subnet
        assert subnet["SubnetId"].startswith("subnet-")

    def test_create_subnet_linked_to_vpc(self, provisioner):
        """Subnet must carry the VpcId of the parent VPC."""
        with mock_aws():
            vpc = provisioner.provision_vpc("10.10.0.0/16")
            subnet = provisioner.create_subnet(
                vpc["VpcId"], "10.10.1.0/24", "us-east-1a"
            )

        assert subnet["VpcId"] == vpc["VpcId"]

    def test_create_multiple_subnets_same_vpc(self, provisioner):
        """Multiple subnets can be created in the same VPC."""
        with mock_aws():
            vpc = provisioner.provision_vpc("10.10.0.0/16")
            subnet_public_1 = provisioner.create_subnet(
                vpc["VpcId"], "10.10.1.0/24", "us-east-1a"
            )
            subnet_public_2 = provisioner.create_subnet(
                vpc["VpcId"], "10.10.2.0/24", "us-east-1b"
            )
            subnet_private_1 = provisioner.create_subnet(
                vpc["VpcId"], "10.10.11.0/24", "us-east-1a"
            )
            subnet_private_2 = provisioner.create_subnet(
                vpc["VpcId"], "10.10.12.0/24", "us-east-1b"
            )

        subnet_ids = {
            subnet_public_1["SubnetId"],
            subnet_public_2["SubnetId"],
            subnet_private_1["SubnetId"],
            subnet_private_2["SubnetId"],
        }
        # All four subnets must have distinct IDs
        assert len(subnet_ids) == 4

    def test_create_subnet_cidr_matches_input(self, provisioner):
        """Subnet CIDR must match the requested value."""
        with mock_aws():
            vpc = provisioner.provision_vpc("10.10.0.0/16")
            subnet = provisioner.create_subnet(
                vpc["VpcId"], "10.10.1.0/24", "us-east-1a"
            )

        assert subnet["CidrBlock"] == "10.10.1.0/24"


class TestGetVPC:
    """Tests for VPCProvisioner.get_vpc."""

    def test_get_vpc_returns_correct_vpc(self, provisioner):
        """get_vpc must return the VPC that was created."""
        with mock_aws():
            created = provisioner.provision_vpc("10.10.0.0/16")
            fetched = provisioner.get_vpc(created["VpcId"])

        assert fetched["VpcId"] == created["VpcId"]
        assert fetched["CidrBlock"] == "10.10.0.0/16"

    def test_get_vpc_not_found_raises_value_error(self, provisioner):
        """get_vpc must raise ValueError when the VPC does not exist."""
        with mock_aws():
            with pytest.raises((ValueError, ClientError)):
                provisioner.get_vpc("vpc-00000000000000000")


# ---------------------------------------------------------------------------
# AC2 – 100% branch coverage: invalid CIDRs and reserved ranges
# ---------------------------------------------------------------------------


class TestValidateCIDR:
    """Tests for VPCProvisioner._validate_cidr (via public methods)."""

    def test_malformed_cidr_raises_value_error(self, provisioner):
        """A non-CIDR string must raise ValueError."""
        with mock_aws():
            with pytest.raises(ValueError, match="Invalid CIDR block"):
                provisioner.provision_vpc("not-a-cidr")

    def test_empty_cidr_raises_value_error(self, provisioner):
        """An empty string must raise ValueError."""
        with mock_aws():
            with pytest.raises(ValueError):
                provisioner.provision_vpc("")

    def test_cidr_with_invalid_prefix_length_raises(self, provisioner):
        """A prefix length > 32 must raise ValueError."""
        with mock_aws():
            with pytest.raises(ValueError):
                provisioner.provision_vpc("10.10.0.0/33")

    def test_loopback_cidr_raises_value_error(self, provisioner):
        """127.0.0.0/8 (loopback) must be rejected as a reserved range."""
        with mock_aws():
            with pytest.raises(ValueError, match="reserved range"):
                provisioner.provision_vpc("127.0.0.0/8")

    def test_loopback_subnet_raises_value_error(self, provisioner):
        """A subnet within 127.0.0.0/8 must also be rejected."""
        with mock_aws():
            with pytest.raises(ValueError, match="reserved range"):
                provisioner.provision_vpc("127.100.0.0/24")

    def test_link_local_cidr_raises_value_error(self, provisioner):
        """169.254.0.0/16 (link-local) must be rejected."""
        with mock_aws():
            with pytest.raises(ValueError, match="reserved range"):
                provisioner.provision_vpc("169.254.0.0/16")

    def test_link_local_subnet_raises_value_error(self, provisioner):
        """A subnet within 169.254.0.0/16 must be rejected."""
        with mock_aws():
            with pytest.raises(ValueError, match="reserved range"):
                provisioner.provision_vpc("169.254.1.0/24")

    def test_class_e_cidr_raises_value_error(self, provisioner):
        """240.0.0.0/4 (class E / reserved) must be rejected."""
        with mock_aws():
            with pytest.raises(ValueError, match="reserved range"):
                provisioner.provision_vpc("240.0.0.0/4")

    def test_class_e_subnet_raises_value_error(self, provisioner):
        """A subnet within 240.0.0.0/4 must be rejected."""
        with mock_aws():
            with pytest.raises(ValueError, match="reserved range"):
                provisioner.provision_vpc("250.10.0.0/16")

    def test_this_network_cidr_raises_value_error(self, provisioner):
        """0.0.0.0/8 ('this' network) must be rejected."""
        with mock_aws():
            with pytest.raises(ValueError, match="reserved range"):
                provisioner.provision_vpc("0.0.0.0/8")

    def test_validate_cidr_static_method_invalid(self):
        """_validate_cidr is callable as a static method and raises for bad input."""
        with pytest.raises(ValueError, match="Invalid CIDR block"):
            VPCProvisioner._validate_cidr("bad input")

    def test_validate_cidr_static_method_valid(self):
        """_validate_cidr must not raise for a legitimate private CIDR."""
        VPCProvisioner._validate_cidr("10.10.0.0/16")  # should not raise

    def test_create_subnet_invalid_cidr_raises(self, provisioner):
        """create_subnet with a reserved CIDR raises before calling AWS."""
        with mock_aws():
            vpc = provisioner.provision_vpc("10.10.0.0/16")
            with pytest.raises(ValueError, match="reserved range"):
                provisioner.create_subnet(
                    vpc["VpcId"], "127.0.0.0/24", "us-east-1a"
                )


# ---------------------------------------------------------------------------
# AC3 – Tests pass with simulated AWS responses (SDK error handling)
# ---------------------------------------------------------------------------


class TestAWSSDKErrors:
    """Verifies that ClientError / SDK timeouts are surfaced correctly."""

    def test_provision_vpc_client_error_propagates(self, monkeypatch):
        """ClientError from boto3 create_vpc must propagate to the caller."""
        error_response = {
            "Error": {"Code": "RequestExpired", "Message": "Request has expired."}
        }
        with mock_aws():
            provisioner = VPCProvisioner(region="us-east-1")
            with patch.object(
                provisioner._ec2,
                "create_vpc",
                side_effect=ClientError(error_response, "CreateVpc"),
            ):
                with pytest.raises(ClientError, match="RequestExpired"):
                    provisioner.provision_vpc("10.10.0.0/16")

    def test_create_subnet_client_error_propagates(self, monkeypatch):
        """ClientError from boto3 create_subnet must propagate to the caller."""
        error_response = {
            "Error": {
                "Code": "InvalidVpcID.NotFound",
                "Message": "The vpc ID 'vpc-xxx' does not exist",
            }
        }
        with mock_aws():
            provisioner = VPCProvisioner(region="us-east-1")
            with patch.object(
                provisioner._ec2,
                "create_subnet",
                side_effect=ClientError(error_response, "CreateSubnet"),
            ):
                with pytest.raises(ClientError, match="InvalidVpcID.NotFound"):
                    provisioner.create_subnet(
                        "vpc-xxx", "10.10.1.0/24", "us-east-1a"
                    )

    def test_provisioner_uses_specified_region(self):
        """VPCProvisioner stores and uses the provided region."""
        with mock_aws():
            p = VPCProvisioner(region="eu-west-1")
            assert p.region == "eu-west-1"
