import pyautogui
import time
import json
import keyboard
import mouse

pyautogui.MINIMUM_DURATION = 0
pyautogui.MINIMUM_SLEEP = 0
pyautogui.PAUSE = 0

events = []
start_time = None

print("A gravação começará em 5 segundos...")
time.sleep(5)

def on_mouse_move(event):
    if isinstance(event, mouse.MoveEvent):
        events.append({
            "type": "mouse_move",
            "x": event.x,
            "y": event.y,
            "time": time.time() - start_time
        })

def on_mouse_click(event):
    if isinstance(event, mouse.ButtonEvent):
        x, y = mouse.get_position()
        events.append({
            "type": "mouse_click",
            "x": x,
            "y": y,
            "button": event.button,
            "pressed": event.event_type == "down",
            "time": time.time() - start_time
        })

def on_key_press(event):
    events.append({
        "type": "key_press",
        "key": event.name,
        "time": time.time() - start_time
    })

print("Gravação iniciada! Pressione ESC para parar.")
start_time = time.time()

keyboard.on_press(on_key_press)
mouse.hook(on_mouse_move)
mouse.hook(on_mouse_click)

keyboard.wait("esc")

with open("events.json", "w") as f:
    json.dump(events, f, indent=4)

print("Gravação finalizada! Os eventos foram salvos em 'events.json'.")

def replay_events():
    print("A reprodução começará em 5 segundos...")
    time.sleep(5)

    with open("events.json", "r") as f:
        events = json.load(f)

    start_time = time.time()
    for event in events:
        elapsed = event["time"]
        current_time = time.time() - start_time
        delay = elapsed - current_time
        if delay > 0:
            time.sleep(delay)

        if event["type"] == "mouse_move":
            # Define duração zero para movimento imediato
            pyautogui.moveTo(event["x"], event["y"], duration=0)
        elif event["type"] == "mouse_click":
            if event["pressed"]:
                pyautogui.mouseDown(event["x"], event["y"], button=event["button"])
            else:
                pyautogui.mouseUp(event["x"], event["y"], button=event["button"])
        elif event["type"] == "key_press":
            pyautogui.press(event["key"])

print("Reproduzindo eventos...")
while(True): replay_events()
print("Reprodução finalizada!") 