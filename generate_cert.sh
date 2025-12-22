#!/bin/bash
mkdir -p nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/selfsigned.key \
  -out nginx/certs/selfsigned.crt \
  -subj "/C=KE/ST=Nairobi/L=Nairobi/O=ISP/OU=IT/CN=isp.hasalioma.online"
echo "Certificates generated in nginx/certs/"
