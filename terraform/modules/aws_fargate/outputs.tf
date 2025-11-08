# AWS Fargate Module Outputs
# These outputs are referenced in Dativo job configs via {{terraform_outputs.*}}

output "cluster_name" {
  description = "ECS Cluster name"
  value       = aws_ecs_cluster.dativo_cluster.name
}

output "cluster_arn" {
  description = "ECS Cluster ARN"
  value       = aws_ecs_cluster.dativo_cluster.arn
}

output "task_definition_arn" {
  description = "ECS Task Definition ARN (full ARN with revision)"
  value       = aws_ecs_task_definition.dativo_task.arn
}

output "task_definition_family" {
  description = "ECS Task Definition family name"
  value       = aws_ecs_task_definition.dativo_task.family
}

output "service_name" {
  description = "ECS Service name (if created)"
  value       = var.create_service ? aws_ecs_service.dativo_service[0].name : null
}

output "service_arn" {
  description = "ECS Service ARN (if created)"
  value       = var.create_service ? aws_ecs_service.dativo_service[0].id : null
}

output "task_execution_role_arn" {
  description = "IAM Role ARN for ECS task execution"
  value       = aws_iam_role.ecs_task_execution_role.arn
}

output "task_role_arn" {
  description = "IAM Role ARN for ECS task application permissions"
  value       = aws_iam_role.ecs_task_role.arn
}

output "security_group_id" {
  description = "Security Group ID for Fargate tasks"
  value       = aws_security_group.dativo_task_sg.id
}

output "log_group_name" {
  description = "CloudWatch Log Group name"
  value       = aws_cloudwatch_log_group.dativo_logs.name
}

output "endpoint_url" {
  description = "Endpoint URL (placeholder - actual endpoint depends on service type)"
  value       = var.create_service ? "ecs-service://${aws_ecs_service.dativo_service[0].name}" : "ecs-task://${aws_ecs_task_definition.dativo_task.family}"
}

output "all_tags" {
  description = "All tags applied to resources (for verification)"
  value       = local.common_tags
}
