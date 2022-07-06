from aws_cdk.aws_ec2 import SubnetType
from aws_cdk import (
    BundlingOptions,
    Duration,
    aws_ec2 as ec2,
    aws_autoscaling as autoscaling,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
    aws_sns as sns,
    aws_lambda as _lambda,
    aws_autoscaling_hooktargets as hooktargets,
    aws_sns_subscriptions as subscriptions,
    Stack,
)
from constructs import Construct
from constructs import Construct
from . import AWS_AMI, AWS_REGION, AWS_KEYPAIR


class ExampleSystemStack(Stack):
    def __init__(self, scope: Construct, id: str, props, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Autoscale group
        autoscale_group = autoscaling.AutoScalingGroup(
            self,
            "example-autoscale-group",
            vpc=props["vpc"],
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.MEMORY5, ec2.InstanceSize.XLARGE),
            machine_image=ec2.MachineImage.generic_linux({AWS_REGION: AWS_AMI}),
            key_name="{keypair}".format(keypair=AWS_KEYPAIR),
            vpc_subnets=ec2.SubnetSelection(subnet_type=SubnetType.PRIVATE_WITH_NAT),
        )

        asg_dict = {
            "asg_name": autoscale_group.auto_scaling_group_name,
        }
        props.update(asg_dict)

        # Creates a security group for the autoscale group
        sg_example_asg = ec2.SecurityGroup(self, id="sg_example_asg", vpc=props["vpc"], security_group_name="sg_example_asg")

        # Creates a security group for the the autoscale group application load balancer
        sg_alb = ec2.SecurityGroup(self, id="sg_alb", vpc=props["vpc"], security_group_name="sg_example_asg_alb")

        # Allow all egress from ALB to ASG instance
        sg_alb.connections.allow_to(sg_example_asg, ec2.Port.all_tcp(), "To ASG")

        # Allows connections from ALB to ASG instances access port 80
        # where application UI listens
        sg_example_asg.connections.allow_from(sg_alb, ec2.Port.tcp(80), "ALB Ingress")

        # Allow SSH connection between manager and auto-scale group
        sg_example_asg.connections.allow_from(sg_example_asg, ec2.Port.tcp(22), "SSH Ingress")

        sg_example_asg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(22),
            description="ssh",
        )

        # Adds the security group 'sg_example_asg' to the autoscaling group
        autoscale_group.add_security_group(sg_example_asg)

        # Creates an application load balance
        example_alb = elbv2.ApplicationLoadBalancer(
            self,
            "ExampleALB",
            vpc=props["vpc"],
            security_group=sg_alb,
            internet_facing=True,
        )

        # Adds the autoscaling group's instance to be registered as targets on port 80
        example_listener = example_alb.add_listener("Listener", port=80)
        example_listener.add_targets("Target", port=80, protocol=elbv2.ApplicationProtocol.HTTP, targets=[autoscale_group])

        # This creates a "0.0.0.0/0" rule to allow every one to access the ALB
        example_listener.connections.allow_default_port_from_any_ipv4("Open to the world")

        topic_id = "system-autoscale-topic"
        topic = sns.Topic(self, topic_id, display_name="System autoscale topic", topic_name=topic_id)

        # Create role
        asg_topic_pub_role_name = "system-autoscale-topic-publisher-role-"
        asg_topic_pub_role = iam.Role(
            scope=self,
            id=asg_topic_pub_role_name,
            assumed_by=iam.ServicePrincipal("autoscaling.amazonaws.com"),
            role_name=asg_topic_pub_role_name,
            inline_policies=[
                iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(resources=[topic.topic_arn], actions=["sns:Publish"]),
                    ]
                )
            ],
        )

        topic_hook = hooktargets.TopicHook(topic)
        asg_lifecyclehook_name = "system-autoscale-lifecycle-hook"
        autoscale_group.add_lifecycle_hook(
            id=asg_lifecyclehook_name,
            lifecycle_transition=autoscaling.LifecycleTransition.INSTANCE_LAUNCHING,
            default_result=autoscaling.DefaultResult.ABANDON,
            heartbeat_timeout=Duration.minutes(15),
            lifecycle_hook_name=asg_lifecyclehook_name,
            notification_target=topic_hook,
            role=asg_topic_pub_role,
        )

        # Create role
        lambda_role_name = "system-autoscale-topic-lamda-role"
        lambda_role = iam.Role(
            scope=self,
            id=lambda_role_name,
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            role_name=lambda_role_name,
            inline_policies=[
                iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(resources=["arn:aws:logs:*:*:*"], actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]),
                        iam.PolicyStatement(resources=["*"], actions=["autoscaling:CompleteLifecycleAction"]),
                    ]
                )
            ],
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSLambdaExecute"),
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonSSMAutomationRole"),
            ],
        )

        lambda_sg_name = "system-autoscale-launching-lambda-sg"
        lambda_sg = ec2.SecurityGroup(self, lambda_sg_name, security_group_name=lambda_sg_name, vpc=props["vpc"], allow_all_outbound=True)

        # Defines an AWS Lambda resource
        lambda_name = "system-autoscale-launch-lambda"
        asg_launch = _lambda.Function(
            self,
            lambda_name,
            runtime=_lambda.Runtime.PYTHON_3_9,
            function_name=lambda_name,
            description="Lambda function deployed to handle launching Controller instances.",
            code=_lambda.Code.from_asset(
                "./scale_manager/lambda",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_9.bundling_image,
                    command=["bash", "-c", "pip install -r requirements.txt -t /asset-output && cp -dR . /asset-output"],
                ),
            ),
            handler="asg_launching.handler",
            role=lambda_role,
            security_groups=[lambda_sg, sg_example_asg],
            timeout=Duration.minutes(10),
            vpc=props["vpc"],
        )

        topic.add_subscription(subscriptions.LambdaSubscription(asg_launch))
