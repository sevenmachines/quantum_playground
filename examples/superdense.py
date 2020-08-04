from quantum_session import QuantumSession
from braket.circuits import Circuit
import boto3

import binascii

def text_to_bits(text, encoding='utf-8', errors='surrogatepass'):
    bits = bin(int.from_bytes(text.encode(encoding, errors), 'big'))[2:]
    return bits.zfill(8 * ((len(bits) + 7) // 8))

def text_from_bits(bits, encoding='utf-8', errors='surrogatepass'):
    n = int(bits, 2)
    return n.to_bytes((n.bit_length() + 7) // 8, 'big').decode(encoding, errors) or '\0'

def split_bits(bits):
    return [bits[x:x+2] for x in range(0, len(bits), 2)]

def merge_bits(bits):
    return ''.join(bits)

def bell():
    return Circuit().h(0).cnot(0, 1)

def inverse_bell():
    return Circuit().cnot(0, 1).h(0) 

def quantum_encode(code):
    # 00 -> I
    # 01 -> X
    # 10 -> Z
    # 11 -> ZX
    if code == '00':
        circ = Circuit().i(0)
    elif code == '01':
        circ = Circuit().x(0)
    elif code == '10':
        circ = Circuit().z(0)
    elif code == '11':
        circ = Circuit().z(0).x(0)
    else:
        raise QuantumEncodingNotSupported(code)
    return circ

def superdense(code):
    circ = Circuit()
    circ.add_circuit(bell())
    circ.add_circuit(quantum_encode(code))
    circ.add_circuit(inverse_bell())
    return circ

def encode(text):
    bits = text_to_bits(text)
    codes = split_bits(bits)
    return codes

def decode(bits):
    decoded_bits = merge_bits(bits)
    decoded_text = text_from_bits(decoded_bits)
    return decoded_text

text = 'hello'
codes = encode(text)
print("Alice superdense sending '{}', '{}'".format(text, ''.join(codes)))
decoded_bits = []

qsess = QuantumSession(region_name='us-west-1', device_type='qs3')
for code in codes:
    circ = superdense(code=code)
    result = qsess.run_circuit(circuit=circ)
    key = list(result.keys())[0]
    print("Alice: '{}' ---> '{}' :Bob".format(code, key))
    decoded_bits.append(key)

decoded_text = decode(decoded_bits)
print("Bob received '{}'".format(decoded_text))


