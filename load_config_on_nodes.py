import yaml
import os
import pprint
import tarfile
from netmiko import ConnectHandler
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor


def get_server_ip():
    try:
        # Connect to an external server to determine the primary IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # Google's public DNS server
            ip_address = s.getsockname()[0]
        return ip_address
    except Exception as e:
        print(f"Error retrieving IP. Please manually hardcode the IP of the server into the script")
        return None


def start_http_server():
    server = HTTPServer(('0.0.0.0', 8000), SimpleHTTPRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down the server.")
        server.server_close()


def load_config(node):
    if node['kind'] == 'juniper_vjunosrouter':
        router = {
            'device_type': 'juniper_junos',
            'ip': node['mgmt-ipv4'],
            'username': 'admin',
            'password': 'admin@123'
            }

        # Copy the clab startup config to the lab_configs dir for the node
        docker_cmd = f"docker cp clab-{user_directory}-{node['name']}:/juniper.conf ./{user_directory}/lab_configs/{node['name']}/juniper.conf"
        print(docker_cmd)
        subprocess.run(docker_cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        # Connect
        net_connect = ConnectHandler(**router)
        net_connect.config_mode()

        # First load the initial config from clab with a load override
        cmd = f"load override http://{server_ip}:8000/{user_directory}/lab_configs/{node['name']}/juniper.conf routing-instance mgmt_junos"
        net_connect.send_command(cmd, expect_string=r'\]')

        # Add the target config with load set
        cmd = f"load set http://{server_ip}:8000/{user_directory}/lab_configs/{node['name']}/{config_filename} routing-instance mgmt_junos"
        net_connect.send_command(cmd, expect_string=r'\]')
        net_connect.commit()
        net_connect.disconnect()


server_ip = get_server_ip()
server_thread = threading.Thread(target=start_http_server, daemon=True)
server_thread.start()

user_directory = input('Enter the lab directory (ex. three-routers): ')
config_filename = input('Enter configuration filename (ex. basic.addressing.cfg): ')
for filename in os.listdir(user_directory):
    if filename.endswith('clab.yml'):
        topology_file = os.path.join(user_directory, filename)

with open(topology_file, 'r') as file:
    clab_topology = yaml.safe_load(file)

clab_nodes = [{"name": key, **value} for key, value in clab_topology["topology"]["nodes"].items()]

with ThreadPoolExecutor(max_workers=5) as executor:
    executor.map(load_config, clab_nodes)
