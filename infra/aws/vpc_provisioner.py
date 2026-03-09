"""
VPCProvisioner – provisions AWS VPC and networking components via the AWS SDK.

Usage::

    provisioner = VPCProvisioner(region="us-east-1")
    vpc = provisioner.provision_vpc("10.10.0.0/16")
    subnet = provisioner.create_subnet(vpc["VpcId"], "10.10.1.0/24", "us-east-1a")

The class mirrors the Terraform configuration in infra/aws/vpc.tf and is tested
with moto's EC2 mock backend.

Edge cases handled:
- Invalid CIDR blocks (malformed strings, /33 masks, etc.)
- Reserved IPv4 ranges (loopback 127/8, link-local 169.254/16, class-E 240/4,
  "this" network 0/8)
- AWS SDK timeouts (botocore.exceptions.ClientError propagated to callers)
"""

from __future__ import annotations

import ipaddress
from typing import Any

import boto3
from botocore.exceptions import ClientError

# IPv4 ranges that are reserved and must not be used for VPC CIDRs
_RESERVED_RANGES: list[ipaddress.IPv4Network] = [
    ipaddress.ip_network("0.0.0.0/8"),     # "This" network (RFC 1122)
    ipaddress.ip_network("127.0.0.0/8"),   # Loopback (RFC 1122)
    ipaddress.ip_network("169.254.0.0/16"),# Link-local (RFC 3927)
    ipaddress.ip_network("240.0.0.0/4"),   # Reserved / Class E (RFC 1112)
]


class VPCProvisioner:
    """Creates and configures AWS VPC networking resources.

    Parameters
    ----------
    region:
        AWS region where resources will be created (default: ``"us-east-1"``).
    """

    def __init__(self, region: str = "us-east-1") -> None:
        self.region = region
        self._ec2 = boto3.client("ec2", region_name=region)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def provision_vpc(self, cidr_block: str) -> dict[str, Any]:
        """Create a VPC with DNS support and hostnames enabled.

        Parameters
        ----------
        cidr_block:
            IPv4 CIDR for the VPC (e.g. ``"10.10.0.0/16"``).

        Returns
        -------
        dict
            VPC object returned by the AWS EC2 API, including ``VpcId``.

        Raises
        ------
        ValueError
            If *cidr_block* is syntactically invalid or overlaps a reserved range.
        botocore.exceptions.ClientError
            On any AWS API error (includes SDK timeout scenarios).
        """
        self._validate_cidr(cidr_block)

        response = self._ec2.create_vpc(CidrBlock=cidr_block)
        vpc = response["Vpc"]
        vpc_id = vpc["VpcId"]

        # Enable DNS hostnames and DNS resolution (mirrors vpc.tf settings)
        self._ec2.modify_vpc_attribute(
            VpcId=vpc_id,
            EnableDnsHostnames={"Value": True},
        )
        self._ec2.modify_vpc_attribute(
            VpcId=vpc_id,
            EnableDnsSupport={"Value": True},
        )

        return vpc

    def create_subnet(
        self,
        vpc_id: str,
        cidr_block: str,
        availability_zone: str,
    ) -> dict[str, Any]:
        """Create a subnet and associate it with the given VPC.

        Parameters
        ----------
        vpc_id:
            Target VPC identifier (e.g. ``"vpc-0123456789abcdef0"``).
        cidr_block:
            Subnet CIDR block; must be a sub-range of the VPC CIDR.
        availability_zone:
            AWS AZ name (e.g. ``"us-east-1a"``).

        Returns
        -------
        dict
            Subnet object from the AWS EC2 API, including ``SubnetId``
            and ``VpcId``.

        Raises
        ------
        ValueError
            If *cidr_block* is invalid or overlaps a reserved range.
        botocore.exceptions.ClientError
            On any AWS API error.
        """
        self._validate_cidr(cidr_block)

        response = self._ec2.create_subnet(
            VpcId=vpc_id,
            CidrBlock=cidr_block,
            AvailabilityZone=availability_zone,
        )
        return response["Subnet"]

    def get_vpc(self, vpc_id: str) -> dict[str, Any]:
        """Retrieve an existing VPC by its identifier.

        Parameters
        ----------
        vpc_id:
            The VPC identifier (e.g. ``"vpc-0123456789abcdef0"``).

        Returns
        -------
        dict
            VPC attributes from the AWS EC2 API.

        Raises
        ------
        ValueError
            If no VPC with *vpc_id* exists in the account/region.
        botocore.exceptions.ClientError
            On any AWS API error.
        """
        response = self._ec2.describe_vpcs(VpcIds=[vpc_id])
        vpcs = response.get("Vpcs", [])
        if not vpcs:
            raise ValueError(f"VPC '{vpc_id}' not found")
        return vpcs[0]

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_cidr(cidr_block: str) -> None:
        """Raise ValueError for invalid or reserved CIDR blocks.

        Parameters
        ----------
        cidr_block:
            IPv4 CIDR string to validate.

        Raises
        ------
        ValueError
            If the CIDR is malformed or overlaps a reserved IPv4 range.
        """
        try:
            network = ipaddress.ip_network(cidr_block, strict=False)
        except ValueError as exc:
            raise ValueError(
                f"Invalid CIDR block '{cidr_block}': {exc}"
            ) from exc

        for reserved in _RESERVED_RANGES:
            if network.overlaps(reserved):
                raise ValueError(
                    f"CIDR block '{cidr_block}' overlaps reserved range '{reserved}'"
                )
