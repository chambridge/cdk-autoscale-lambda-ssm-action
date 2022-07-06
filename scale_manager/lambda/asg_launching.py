import boto3
import logging
import json
import time

if len(logging.getLogger().handlers) > 0:
    # The Lambda environment pre-configures a handler logging to stderr. If a handler is already configured,
    # `.basicConfig` does not execute. Thus we set the level directly.
    logging.getLogger().setLevel(logging.INFO)
else:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger()


def get_notification_sns_msg(notification):
    message_dict = {}
    records = notification.get("Records", [])
    for record in records:
        if record.get("EventSource") != "aws:sns":
            continue
        sns_data = record.get("Sns", {})
        message = sns_data.get("Message", "{}")
        try:
            message_dict = json.loads(message)
        except:
            logger.error(f"Cannot parse Sns message. Details:{message}")
        if message_dict:
            break
    return message_dict


def handler(notification, context):
    logger.info(f"Request receieved. Details:{notification}")
    client = boto3.client("ssm")
    message_dict = get_notification_sns_msg(notification)
    instance_id = message_dict.get("EC2InstanceId")
    if not instance_id:
        return "Error processing notification."

    command_call = time.time_ns()
    temp_file = f"/tmp/run-command-{command_call}.txt"
    response = client.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Parameters={
            "commands": [
                f"echo 'This file is from a run command via SSM Agent for instance {instance_id}.' > {temp_file}",
                f"if [ -e {temp_file} ]; then echo -n True; else echo -n False; fi",
            ]
        },
    )
    command_id = response["Command"]["CommandId"]
    tries = 0
    output = "False"
    while tries < 20:
        tries = tries + 1
        try:
            time.sleep(2)
            result = client.get_command_invocation(
                CommandId=command_id,
                InstanceId=instance_id,
            )
            if result["Status"] == "InProgress":
                continue
            output = result["StandardOutputContent"]
            break
        except client.exceptions.InvocationDoesNotExist:
            continue

    as_client = boto3.client("autoscaling")
    response = as_client.complete_lifecycle_action(
        LifecycleHookName=message_dict.get("LifecycleHookName"),
        LifecycleActionToken=message_dict.get("LifecycleActionToken"),
        AutoScalingGroupName=message_dict.get("AutoScalingGroupName"),
        LifecycleActionResult="CONTINUE",
        InstanceId=instance_id,
    )

    return output == "True"
