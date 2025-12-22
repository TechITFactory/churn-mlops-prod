variable "aws_region" {
  type        = string
  description = "AWS region to deploy EKS"
  default     = "us-east-1"
}

variable "cluster_name" {
  type        = string
  description = "EKS cluster name"
  default     = "churn-mlops"
}

variable "node_instance_type" {
  type        = string
  description = "Instance type for worker nodes"
  default     = "t3.small"
}
