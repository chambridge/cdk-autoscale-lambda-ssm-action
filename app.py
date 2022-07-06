#!/usr/bin/env python3
import os

import aws_cdk as cdk
from scale_manager.net import ExampleNetworkStack
from scale_manager.systems import ExampleSystemStack


app = cdk.App()
props = {}
en_stack = ExampleNetworkStack(app, "ExampleNetworkStack", props)

es_stack = ExampleSystemStack(app, "ExampleSystemStack", en_stack.outputs)
es_stack.add_dependency(en_stack)

app.synth()
