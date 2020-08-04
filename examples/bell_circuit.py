from quantum_session import QuantumSession
from braket.circuits import Circuit

qsess = QuantumSession(region_name='us-west-1', device_type='qs3')
# Creates the circuit (https://wikipedia.org/wiki/Bell_state)
bell = Circuit().h(0).cnot(0, 1)
result = qsess.run_circuit(circuit=bell)
print(result)


