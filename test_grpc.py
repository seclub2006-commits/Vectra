import grpc
import core_pb2
import core_pb2_grpc

def main():
    channel = grpc.insecure_channel('localhost:9876')
    stub = core_pb2_grpc.CoreServiceStub(channel)
    req = core_pb2.CreateConnectorRequest(
        name='test_manual',
        exchange_id='bitget',
        testnet=True,
        api_key='test_key',
        api_secret='test_secret',
        api_passphrase='test_pass',
        product_type='USDT-FUTURES'
    )
    try:
        resp = stub.CreateConnector(req)
        print(f"Response: success={resp.success}, message={resp.message}")
    except grpc.RpcError as e:
        print(f"gRPC error: {e.code()} - {e.details()}")

if __name__ == '__main__':
    main()