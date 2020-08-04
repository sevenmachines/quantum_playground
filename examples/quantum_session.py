import boto3
from braket.aws import AwsQuantumSimulator, AwsQuantumSimulatorArns, AwsSession
from braket.circuits import Circuit

class QuantumSession(object):

    @staticmethod
    def list_arns():
        regions = ['us-west-1', 'us-west-2', 'us-east-1']
        for region_name in regions:
            boto_session = boto3.session.Session(region_name=region_name)
            aws_session = AwsSession(boto_session=boto_session)
            bc = aws_session.braket_client
            simulators = aws_session.braket_client.describe_quantum_simulators()['quantumSimulators']
            available_simulators = [x['arn'] for x in simulators if x['status'] == 'AVAILABLE']
            print('REGION: {}: {}'.format(region_name, available_simulators))
        return

    def __init__(self, region_name='us-west-1', device_type='simulator'):
        self._setup_session(region_name=region_name)
        self._setup_quantum_device(device_type=device_type)

    def _setup_session(self, region_name):
        boto_session = boto3.session.Session(region_name=region_name)
        self.aws_session = AwsSession(boto_session=boto_session)
        # Sets the AWS Account ID using STS
        aws_account_id = boto_session.client("sts").get_caller_identity()["Account"]
        # Specifies the S3 bucket to use for job output
        self.s3_folder = (f"braket-output-{aws_account_id}", "folder-name")

    def _setup_quantum_device(self, device_type):
        # Sets the quantum device to run the circuit on
        if device_type == 'simulator' or device_type == 'qs1':
            device_arn = "arn:aws:aqx:::quantum-simulator:aqx:qs1"
        elif device_type == 'qs2':
            device_arn = "arn:aws:aqx:::quantum-simulator:aqx:qs2"
        elif device_type == 'qs3':
            device_arn = "arn:aws:aqx:::quantum-simulator:aqx:qs3"
        elif device_type == 'ionq':
            device_arn = "arn:aws:aqx:::qpu:ionq"
        elif device_type == 'rigeti':
            device_arn = "arn:aws:aqx:::qpu:rigeti"
        else:
            raise QuantumDeviceTypeNotSupported(device_type)
        self.device = AwsQuantumSimulator(arn=device_arn,
                                        aws_session=self.aws_session)

    def run_circuit(self, circuit):
        # Executes the circuit and displays the results
        task = self.device.run(circuit, self.s3_folder)
        result = task.result().measurement_counts
        return result


