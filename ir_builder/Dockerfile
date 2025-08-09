ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python and any other dependencies
RUN apk add --no-cache python3 py3-pip

# Create a virtual environment
RUN python3 -m venv /opt/venv

# Copy the requirements file and install dependencies
# This is the new part
COPY requirements.txt .
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy your application files
COPY app /app

# Set the PATH to include the virtual environment's executables
ENV PATH="/opt/venv/bin:$PATH"

# Copy the entrypoint script
COPY run.sh /
RUN chmod a+x /run.sh

# The command to run the add-on
CMD [ "/run.sh" ]