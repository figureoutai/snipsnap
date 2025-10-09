# register service as scalable
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/aws-hackathon-2025-ecs/video-processing-task-def-service-vm7gkfrp \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 0 --max-capacity 4

# output
# {"ScalableTargetARN": "arn:aws:application-autoscaling:us-east-1:975049899047:scalable-target/0ec561e9362ac621422c87ccfafec797cd18"}

# target-tracking using metric math: messages per task ~= 1
# Target-tracking: keep ~1 message per running task
aws application-autoscaling put-scaling-policy \
  --policy-name backlog-per-task \
  --service-namespace ecs \
  --resource-id service/aws-hackathon-2025-ecs/video-processing-task-def-service-vm7gkfrp \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 1.0,
    "ScaleInCooldown": 60,
    "ScaleOutCooldown": 30,
    "CustomizedMetricSpecification": {
      "Metrics": [
        {
          "Id": "m1",
          "MetricStat": {
            "Metric": {
              "Namespace": "AWS/SQS",
              "MetricName": "ApproximateNumberOfMessagesVisible",
              "Dimensions": [
                {"Name":"QueueName","Value":"sqs-hackathon-2025"}
              ]
            },
            "Stat": "Average"
          },
          "ReturnData": false
        },
        {
          "Id": "m2",
          "MetricStat": {
            "Metric": {
              "Namespace": "AWS/ECS",
              "MetricName": "DesiredTaskCount",
              "Dimensions": [
                {"Name":"ClusterName","Value":"aws-hackathon-2025-ecs"},
                {"Name":"ServiceName","Value":"video-processing-task-def-service-vm7gkfrp"}
              ]
            },
            "Stat": "Average"
          },
          "ReturnData": false
        },
        {
          "Id": "e1",
          "Expression": "m1/IF(m2>0,m2,1)",
          "Label": "BacklogPerTask",
          "ReturnData": true
        }
      ]
    }
  }'

# output
# {
#     "PolicyARN": "arn:aws:autoscaling:us-east-1:975049899047:scalingPolicy:61e9362a-c621-422c-87cc-fafec797cd18:resource/ecs/service/aws-hackathon-2025-ecs/video-processing-task-def-service-vm7gkfrp:policyName/backlog-per-task",
#     "Alarms": [
#         {
#             "AlarmName": "TargetTracking-service/aws-hackathon-2025-ecs/video-processing-task-def-service-vm7gkfrp-AlarmHigh-f27bc6d0-9ff5-4124-abde-368684cc8927",
#             "AlarmARN": "arn:aws:cloudwatch:us-east-1:975049899047:alarm:TargetTracking-service/aws-hackathon-2025-ecs/video-processing-task-def-service-vm7gkfrp-AlarmHigh-f27bc6d0-9ff5-4124-abde-368684cc8927"
#         },
#         {
#             "AlarmName": "TargetTracking-service/aws-hackathon-2025-ecs/video-processing-task-def-service-vm7gkfrp-AlarmLow-aa385898-fdbb-4439-8998-6532a62ddb0f",
#             "AlarmARN": "arn:aws:cloudwatch:us-east-1:975049899047:alarm:TargetTracking-service/aws-hackathon-2025-ecs/video-processing-task-def-service-vm7gkfrp-AlarmLow-aa385898-fdbb-4439-8998-6532a62ddb0f"
#         }
#     ]
# }


# Create a step-scaling policy that adds exactly +1 task when its alarm fires.
aws application-autoscaling put-scaling-policy \
  --region us-east-1 \
  --service-namespace ecs \
  --resource-id service/aws-hackathon-2025-ecs/video-processing-task-def-service-vm7gkfrp \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-type StepScaling \
  --policy-name kick-from-zero \
  --step-scaling-policy-configuration '{
    "AdjustmentType": "ChangeInCapacity",
    "Cooldown": 60,
    "MetricAggregationType": "Average",
    "StepAdjustments": [
      { "MetricIntervalLowerBound": 0, "ScalingAdjustment": 1 }
    ]
  }'

# output
# {
#     "PolicyARN": "arn:aws:autoscaling:us-east-1:975049899047:scalingPolicy:61e9362a-c621-422c-87cc-fafec797cd18:resource/ecs/service/aws-hackathon-2025-ecs/video-processing-task-def-service-vm7gkfrp:policyName/kick-from-zero",
#     "Alarms": []
# }


aws cloudwatch put-metric-alarm \
  --region us-east-1 \
  --alarm-name sqs-hackathon-2025-one-or-more-msgs \
  --namespace AWS/SQS \
  --metric-name ApproximateNumberOfMessagesVisible \
  --dimensions Name=QueueName,Value=sqs-hackathon-2025 \
  --statistic Average \
  --period 60 \
  --evaluation-periods 1 \
  --datapoints-to-alarm 1 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --treat-missing-data notBreaching \
  --alarm-actions "arn:aws:autoscaling:us-east-1:975049899047:scalingPolicy:61e9362a-c621-422c-87cc-fafec797cd18:resource/ecs/service/aws-hackathon-2025-ecs/video-processing-task-def-service-vm7gkfrp:policyName/kick-from-zero"
