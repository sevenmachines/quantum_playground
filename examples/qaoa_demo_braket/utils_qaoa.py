# imports
from datetime import datetime
import numpy as np
import tarfile
import os
import pickle

# AWS imports
import boto3
from braket.circuits import Circuit
from braket.aws import AwsQuantumSimulator, AwsSession
from botocore.session import get_session

# setup credentials and session
creds = get_session().get_credentials()
session = boto3.Session(aws_access_key_id=creds.access_key, aws_secret_access_key=creds.secret_key,
                        aws_session_token=creds.token, region_name="us-west-1")
aws_session = AwsSession(boto_session=session)

# setup client
braket_client = aws_session.braket_client


# function to submit training job
def kickoff_train(circuit_depth, hardware="ml.m4.xlarge", my_python_script="qaoa_hpo.py"):
    """
    function to submit Braket training job using boto3
    hit create_quantum_job API with JSON formatted file specifying the job
    """

    # run training job tagged with custom job name
    project_name = 'qaoa-' + str(circuit_depth)
    job_name = project_name + '-' + datetime.strftime(datetime.now(), '%Y%m%d%H%M%S')
    print('jobName with time stamp:', job_name)

    # call API
    quantum_job_arn = braket_client.create_quantum_job(
        jobName=job_name,
        resourceConfig={
            "instanceCount": 1,
            "instanceType": hardware,
            "volumeSizeInGb": 50
        },
        outputDataConfig={
            "s3OutputPath": "s3://hybrid-job-mjas/results"
        },
        stoppingCondition={
            "maxRuntimeInSeconds": 86400
        },
        sagemakerRoleArn="arn:aws:iam::465542368797:role/AmazonBraketJobExecutionRole",
        inputScriptConfig={
            "scriptS3Bucket": "hybrid-job-mjas",
            "scriptS3ObjectKey": my_python_script
        },
        metricDefinitions=[{
            'name': "cost_avg",
            'regex': "cost_avg=(.*?);"
        }],
        hyperParameters={
            'p': str(circuit_depth),
        },
    )

    # print quantum Job ARN with date, status code etc.
    print(quantum_job_arn)

    # return job name
    return job_name


# custom function for retrieving data from S3 and postprocessing
def postprocess(job_name):
    """
    function for postprocessing of job
    """
    # get the results from S3
    # s3.download_file('BUCKET_NAME', 'OBJECT_NAME', 'FILE_NAME')
    object_key = 'results/{}/output/model.tar.gz'.format('AQxJob-' + job_name)
    tempfile = '/tmp/model.tar.gz'
    s3_client = session.client("s3")
    s3_client.download_file('hybrid-job-mjas', object_key, tempfile)

    # unzip the results
    tar = tarfile.open(tempfile, "r:gz")
    tar.extractall(path='/tmp')

    # load the results into the notebook
    out = pickle.load(open('/tmp/out.pckl', "rb"))

    p = out['p']
    N = out['N']
    ENERGY_OPTIMAL = out['ENERGY_OPTIMAL']
    BITSTRING = out['BITSTRING']
    result_energy = out['result_energy']
    result_angle = out['result_angle']

    # clean-up temporary files
    os.remove(tempfile)

    print('Optimal energy from managed job:', ENERGY_OPTIMAL)
    print('Optimal bit-string from managed job:', BITSTRING)

    gamma = result_angle[:p]
    beta = result_angle[p:]
    pa = np.arange(1, p + 1)

    return p, N, ENERGY_OPTIMAL, BITSTRING, result_energy, result_angle, gamma, beta, pa


# helper function to implement ZZ gate on qubits q1, q2 with angle gamma
# this is workaround as zz-gate is not supported by schroedinger simulator
def ZZgate(q1, q2, gamma):
    """
    function that returns a circuit implementing exp(-i \gamma Z_i Z_j)
    """

    # get a circuit
    circ = Circuit()

    # construct diagonal elements (fourth element)
    gate = Circuit().cphaseshift(q1, q2, gamma)
    circ.add(gate)

    # construct third diagonal element
    gate = Circuit().x(q2)
    circ.add(gate)
    gate = Circuit().cphaseshift(q1, q2, -1*gamma)
    circ.add(gate)
    gate = Circuit().x(q2)
    circ.add(gate)

    # construct second diagonal element
    gate = Circuit().x(q1)
    circ.add(gate)
    gate = Circuit().cphaseshift(q1, q2, -1*gamma)
    circ.add(gate)
    gate = Circuit().x(q1)
    circ.add(gate)

    # construct first diagonal element
    gate = Circuit().x(q1)
    circ.add(gate)
    gate = Circuit().x(q2)
    circ.add(gate)
    gate = Circuit().cphaseshift(q1, q2, gamma)
    circ.add(gate)
    gate = Circuit().x(q1)
    circ.add(gate)
    gate = Circuit().x(q2)
    circ.add(gate)

    return circ
