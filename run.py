import socket
from app import create_app

app = create_app()

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

if __name__ == '__main__':
    local_ip = get_local_ip()
    print("\n===================================================")
    print("       EAT SAFE AI Server Running Successfully")
    print("===================================================")
    print(f"👉 Local Access:   http://127.0.0.1:5000")
    print(f"📱 Mobile/Network: http://{local_ip}:5000")
    print("===================================================\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
