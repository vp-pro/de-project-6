# The 6th project

### Description
The task is to build an analytical storage based on Vertica using Data Vault storage model. Data is kept on Amazon s3 service. Data pipeline should be done with a following sequence (s3 - localhost in Docker Container - Vertica STG - Vertica DDS) and implemented with Apache Airflow.