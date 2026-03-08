variable "aws_region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type for the ObservaKit stack"
  type        = string
  default     = "t3.medium" # Minimum recommended for the full stack
}

variable "key_name" {
  description = "Name of an existing EC2 KeyPair to enable SSH access"
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "CIDR block allowed to SSH into the instance"
  type        = string
  default     = "0.0.0.0/0" # In production, restrict this to your IP
}
