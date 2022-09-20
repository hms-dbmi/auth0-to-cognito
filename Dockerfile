FROM public.ecr.aws/lambda/python:3.9

# Set the function to build for
ARG FUNCTION_FILENAME

# Copy function code
COPY ${FUNCTION_FILENAME} ${LAMBDA_TASK_ROOT}/index.py

# Install the function's dependencies using file requirements.txt
# from your project folder.

COPY requirements.txt  .
RUN  pip3 install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD [ "index.handler" ]
