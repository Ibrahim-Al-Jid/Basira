# Static-only fixture with no planned or deployed resources.
resource "aws_instance" "legacy_metadata" {
  ami           = "ami-example"
  instance_type = "t3.micro"
  metadata_options {
    http_tokens = "optional"
  }
  root_block_device {
    encrypted = true
  }
}

resource "aws_instance" "token_required" {
  ami           = "ami-example"
  instance_type = "t3.micro"
  metadata_options {
    http_tokens = "required"
  }
  root_block_device {
    encrypted = true
  }
}
