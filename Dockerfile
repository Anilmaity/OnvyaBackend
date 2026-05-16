# Use the official Python 3.12 image
FROM python:3.12-bullseye

# # Set the timezone and environment variables
ENV TZ=Asia/Kolkata

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# # Install build dependencies
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential \
#     wget \
#     python3-dev \
#     tzdata \
#     && rm -rf /var/lib/apt/lists/*
#
# Download and install TA-Lib from source


# RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
#     tar -xzf ta-lib-0.4.0-src.tar.gz && \
#     cd ta-lib/ && \
#     ./configure && \
#     make && \
#     make install && \
#     rm -rf ta-lib ta-lib-0.4.0-src.tar.gz
#

RUN mkdir /app
WORKDIR /app
# RUN pip install TA-Lib
RUN pip install django_graphql_auth
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
RUN pip install requests==2.25.0

COPY . .
EXPOSE 8000