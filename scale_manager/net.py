from aws_cdk import (
    CfnOutput,
    Stack,
    aws_iam as iam,
)
from aws_cdk.aws_ec2 import Vpc, NatProvider, SubnetConfiguration, SubnetType, SecurityGroup
from constructs import Construct


class ExampleNetworkStack(Stack):
    def __init__(self, scope: Construct, id: str, props, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Subnet configurations for a public and private tier
        subnet1 = SubnetConfiguration(name="PublicNet", subnet_type=SubnetType.PUBLIC, cidr_mask=24)
        subnet2 = SubnetConfiguration(
            name="PrivateNet",
            subnet_type=SubnetType.PRIVATE_WITH_NAT,
            cidr_mask=24,
        )

        vpc = Vpc(
            self,
            "ExampleVPC",
            cidr="10.0.0.0/16",
            enable_dns_hostnames=True,
            enable_dns_support=True,
            max_azs=2,
            nat_gateway_provider=NatProvider.gateway(),
            nat_gateways=1,
            subnet_configuration=[subnet1, subnet2],
        )

        # This will export the VPC's ID in CloudFormation under the key
        # 'vpcid'
        CfnOutput(self, "vpcid", value=vpc.vpc_id)

        # Prepares output attributes to be passed into other stacks
        # In this case, it is our VPC, subnets and public_subnet_id.
        self.output_props = props.copy()
        self.output_props["vpc"] = vpc
        self.output_props["subnets"] = vpc.public_subnets
        self.output_props["public_subnet_id"] = vpc.public_subnets[0].subnet_id

        policy_document = {"Version": "2012-10-17", "Statement": [{"Sid": "VisualEditor0", "Effect": "Allow", "Action": "ec2:CreateKeyPair", "Resource": "*"}]}
        custom_policy_document = iam.PolicyDocument.from_json(policy_document)

    @property
    def outputs(self):
        return self.output_props
