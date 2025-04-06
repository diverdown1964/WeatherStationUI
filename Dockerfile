FROM mcr.microsoft.com/azure-functions/python:4-python3.9

# Install prerequisites
RUN apt-get update && \
    apt-get install -y curl apt-transport-https gnupg2

# Add Microsoft repository
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list

# Install ODBC Driver
RUN apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql18 && \
    ACCEPT_EULA=Y apt-get install -y mssql-tools18 && \
    apt-get install -y unixodbc-dev

# Copy function app files
COPY . /home/site/wwwroot

# Install Python dependencies
RUN cd /home/site/wwwroot && \
    pip install -r requirements.txt 