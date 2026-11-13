FROM tabulario/spark-iceberg:latest
# Thu vien S3A de Spark (Hive client) lam viec voi MinIO + thu vien doc Excel
ADD https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar /opt/spark/jars/
ADD https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar /opt/spark/jars/
RUN chmod 644 /opt/spark/jars/*.jar && pip3 install --no-cache-dir openpyxl==3.1.5 pandas pyarrow
