import asyncio
import logging
from core.server import serve

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    asyncio.run(serve(host='0.0.0.0', port=9876))

if __name__ == '__main__':
    main()