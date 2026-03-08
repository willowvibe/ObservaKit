# ObservaKit AWS Deployment (Terraform)

This module provisions an AWS EC2 instance (`t3.medium` by default) with Docker installed, and automatically pulls and starts the ObservaKit stack using `docker-compose`.

## Prerequisites
- Terraform installed
- AWS credentials configured (`aws configure`)
- An existing EC2 KeyPair in your target region

## Deployment Steps

1. **Initialize Terraform:**
   ```bash
   terraform init
   ```

2. **Review the deployment plan:**
   ```bash
   terraform plan -var="key_name=YOUR_KEYPAIR_NAME"
   ```

3. **Deploy the stack:**
   ```bash
   terraform apply -var="key_name=YOUR_KEYPAIR_NAME"
   ```

4. **Access the application:**
   The output will display the public IP and the Grafana URL (e.g., `http://<public_ip>:3000`).
   It may take 2-3 minutes for the instance to fully boot and pull the Docker images.

## Security Note
By default, this module leaves port 3000 (Grafana) and 8000 (Backend API) open to the internet (`0.0.0.0/0`). Ensure you have changed the default passwords (`admin/admin` for Grafana) or restrict the security group rules in `main.tf` if deploying for production.
