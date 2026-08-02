import requests
import time
task_id = 'd713278b-20f3-41c7-a3fe-9407e6725807'
status_url = f'http://127.0.0.1:8080/api/authoring/status/{task_id}'
start_time = time.time()
while time.time() - start_time < 90:
    try:
        r = requests.get(status_url)
        data = r.json()
        if data['task']['status'] == 'complete':
            print('DONE in', time.time() - start_time, 'seconds!')
            print(data)
            break
        elif data['task']['message'] != 'Extracting motion...':
            print(f"Progress: {data['task']['message']}")
    except Exception as e:
        pass
    time.sleep(5)
