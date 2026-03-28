import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room
import random
import time
import copy

app = Flask(__name__)
app.config["SECRET_KEY"] = "knowledge-conquest-secret"
socketio = SocketIO(app, cors_allowed_origins="*")

ROOMS = {}
BASE_TIME_LIMIT = 15

# =========================
# 題庫：普通 60% / 中等 30% / 超難 10%
# =========================

NORMAL_QUESTIONS = [
    {"type": "數學", "q": "18 + 27 = ?", "options": ["35", "45", "55", "65"], "answer": "45"},
    {"type": "數學", "q": "9 × 8 = ?", "options": ["72", "81", "64", "70"], "answer": "72"},
    {"type": "數學", "q": "144 ÷ 12 = ?", "options": ["10", "11", "12", "13"], "answer": "12"},
    {"type": "數學", "q": "5² = ?", "options": ["10", "20", "25", "15"], "answer": "25"},
    {"type": "常識", "q": "台灣首都是哪裡？", "options": ["台中", "高雄", "台北", "台南"], "answer": "台北"},
    {"type": "常識", "q": "一年有幾個月？", "options": ["10", "11", "12", "13"], "answer": "12"},
    {"type": "科學", "q": "水的化學式是？", "options": ["O2", "H2O", "CO2", "NaCl"], "answer": "H2O"},
    {"type": "科學", "q": "電子帶什麼電？", "options": ["正電", "負電", "中性", "不一定"], "answer": "負電"},
    {"type": "歷史", "q": "第二次世界大戰結束於哪一年？", "options": ["1943", "1945", "1947", "1950"], "answer": "1945"},
    {"type": "英文", "q": "Apple 的中文是？", "options": ["香蕉", "蘋果", "葡萄", "鳳梨"], "answer": "蘋果"},
    {"type": "英文", "q": "Book 的中文是？", "options": ["筆", "桌子", "書", "杯子"], "answer": "書"},
    {"type": "邏輯", "q": "2, 4, 8, 16, 下一個是？", "options": ["18", "24", "32", "36"], "answer": "32"},
]

MEDIUM_QUESTIONS = [
    {"type": "數學", "q": "15 × 8 - 36 ÷ 6 = ?", "options": ["108", "114", "116", "120"], "answer": "114"},
    {"type": "數學", "q": "若 x = 3，則 2x² + 4x = ?", "options": ["30", "24", "18", "12"], "answer": "30"},
    {"type": "數學", "q": "√144 + 6² = ?", "options": ["48", "50", "52", "54"], "answer": "48"},
    {"type": "數學", "q": "一個數的 40% 是 80，原數是多少？", "options": ["200", "180", "160", "120"], "answer": "200"},
    {"type": "邏輯", "q": "3, 6, 12, 24, ? 下一個數字是？", "options": ["30", "36", "48", "60"], "answer": "48"},
    {"type": "邏輯", "q": "A比B大，B比C大，則？", "options": ["C最大", "A最小", "A比C大", "無法判斷"], "answer": "A比C大"},
    {"type": "常識", "q": "世界上面積最大的國家是？", "options": ["中國", "美國", "俄羅斯", "加拿大"], "answer": "俄羅斯"},
    {"type": "常識", "q": "光速約為每秒多少公里？", "options": ["30萬", "3萬", "300萬", "3億"], "answer": "30萬"},
    {"type": "科學", "q": "DNA 的雙螺旋結構由誰提出？", "options": ["牛頓", "達爾文", "華生與克里克", "愛迪生"], "answer": "華生與克里克"},
    {"type": "科學", "q": "地球繞太陽一圈約需多久？", "options": ["30天", "180天", "365天", "730天"], "answer": "365天"},
    {"type": "英文", "q": "Break the ice 的意思是？", "options": ["打破冰塊", "破除尷尬", "很冷", "生氣"], "answer": "破除尷尬"},
    {"type": "觀念", "q": "CPU 的主要功能是？", "options": ["儲存資料", "顯示畫面", "運算與控制", "傳輸網路"], "answer": "運算與控制"},
]

HARD_QUESTIONS = [
    {"type": "超難數學", "q": "1 到 100 中，能被 3 或 5 整除的數共有幾個？", "options": ["47", "46", "48", "49"], "answer": "47"},
    {"type": "超難數學", "q": "若 f(x)=2x+3，則 f(f(2)) = ?", "options": ["11", "13", "15", "17"], "answer": "17"},
    {"type": "超難數學", "q": "等差數列 3, 7, 11, ... 第 20 項為？", "options": ["75", "77", "79", "81"], "answer": "79"},
    {"type": "超難邏輯", "q": "有 3 個開關控制 3 盞燈，只能進房間一次，至少能確定幾盞燈對應關係？", "options": ["1", "2", "3", "0"], "answer": "2"},
    {"type": "超難科學", "q": "哪個粒子不帶電？", "options": ["電子", "質子", "中子", "離子"], "answer": "中子"},
    {"type": "超難觀念", "q": "通貨膨脹最直接代表什麼？", "options": ["物價上升", "股價下跌", "失業率下降", "貨幣消失"], "answer": "物價上升"},
]

CHARACTERS = {
    "slow": {
        "name": "慢速人",
        "desc": "每次答題時間 +5 秒",
    },
    "scholar": {
        "name": "學霸",
        "desc": "可使用 3 次刪除兩個選項",
    },
    "landlord": {
        "name": "霸道地主",
        "desc": "可強制霸佔 1 格鄰近隱藏格",
    },
    "seer": {
        "name": "先知",
        "desc": "可直接看見所有格子的題型",
    },
}


def weighted_question():
    r = random.random()
    if r < 0.6:
        return copy.deepcopy(random.choice(NORMAL_QUESTIONS))
    elif r < 0.9:
        return copy.deepcopy(random.choice(MEDIUM_QUESTIONS))
    else:
        return copy.deepcopy(random.choice(HARD_QUESTIONS))


def create_grid(size):
    grid = []
    for _ in range(size):
        row = []
        for _ in range(size):
            row.append({
                "status": "hidden",   # hidden / owned / blocked
                "owner": None,
                "question": weighted_question()
            })
        grid.append(row)
    return grid


def get_spawn_positions(size, max_players):
    corners = [
        (0, 0),
        (0, size - 1),
        (size - 1, 0),
        (size - 1, size - 1),
    ]
    return corners[:max_players]


def get_adjacent_cells(pos, size):
    x, y = pos
    candidates = [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
    result = []
    for nx, ny in candidates:
        if 0 <= nx < size and 0 <= ny < size:
            result.append((nx, ny))
    return result


def count_owned_cells(room_id, sid):
    room = ROOMS[room_id]
    total = 0
    for row in room["grid"]:
        for cell in row:
            if cell["status"] == "owned" and cell["owner"] == sid:
                total += 1
    return total


def has_available_move(room_id, sid):
    room = ROOMS[room_id]
    if sid not in room["players"]:
        return False

    player = room["players"][sid]
    size = room["board_size"]

    for nx, ny in get_adjacent_cells(player["pos"], size):
        cell = room["grid"][nx][ny]
        if cell["status"] == "hidden":
            return True
    return False


def finish_player_if_stuck(room_id, sid):
    room = ROOMS[room_id]
    if sid not in room["players"]:
        return

    player = room["players"][sid]
    if player["finished"]:
        return

    if sid in room["active_questions"]:
        return

    if not has_available_move(room_id, sid):
        player["finished"] = True
        socketio.emit(
            "system_message",
            {"msg": f"{player['name']} 已無路可走，結束本局。"},
            room=room_id
        )


def try_end_game(room_id):
    room = ROOMS[room_id]
    if room["game_over"]:
        return

    if len(room["players"]) < 2:
        return

    if all(p["finished"] for p in room["players"].values()):
        room["game_over"] = True
        ranking = []
        for sid, p in room["players"].items():
            ranking.append({
                "sid": sid,
                "name": p["name"],
                "count": count_owned_cells(room_id, sid),
                "color": p["color"],
                "character": p["character"],
                "character_name": CHARACTERS[p["character"]]["name"],
            })

        ranking.sort(key=lambda x: x["count"], reverse=True)

        if len(ranking) >= 2 and ranking[0]["count"] == ranking[1]["count"]:
            room["winner_text"] = f"平手！最高皆為 {ranking[0]['count']} 格"
        else:
            room["winner_text"] = f"勝利者：{ranking[0]['name']}（{ranking[0]['character_name']}），共佔領 {ranking[0]['count']} 格"

        socketio.emit(
            "game_over",
            {
                "winner_text": room["winner_text"],
                "ranking": ranking,
            },
            room=room_id
        )


def personalized_room_state(room_id, sid):
    room = ROOMS[room_id]
    player = room["players"].get(sid)

    players_public = {}
    for psid, p in room["players"].items():
        players_public[psid] = {
            "name": p["name"],
            "color": p["color"],
            "pos": list(p["pos"]),
            "finished": p["finished"],
            "character": p["character"],
            "character_name": CHARACTERS[p["character"]]["name"],
            "skills": p["skills"],
            "occupied_count": count_owned_cells(room_id, psid),
        }

    grid_public = []
    for row in room["grid"]:
        public_row = []
        for cell in row:
            c = {
                "status": cell["status"],
                "owner": cell["owner"],
                "type": None,
            }

            if player and player["character"] == "seer":
                c["type"] = cell["question"]["type"]

            public_row.append(c)
        grid_public.append(public_row)

    return {
        "room": room_id,
        "board_size": room["board_size"],
        "max_players": room["max_players"],
        "host_id": room["host_id"],
        "started": room["started"],
        "game_over": room["game_over"],
        "winner_text": room["winner_text"],
        "players": players_public,
        "grid": grid_public,
        "character_defs": CHARACTERS,
    }


def emit_room_state(room_id):
    room = ROOMS[room_id]
    for sid in room["players"]:
        socketio.emit("room_state", personalized_room_state(room_id, sid), room=sid)


def handle_wrong_or_timeout(room_id, sid, x, y, is_timeout=False):
    room = ROOMS[room_id]
    cell = room["grid"][x][y]
    cell["status"] = "blocked"
    cell["owner"] = None

    if sid in room["active_questions"]:
        del room["active_questions"][sid]

    if sid in room["players"]:
        msg = "超時，該格變灰。" if is_timeout else "答錯，該格變灰。"
        socketio.emit("self_message", {"msg": msg}, room=sid)

    finish_player_if_stuck(room_id, sid)
    emit_room_state(room_id)
    try_end_game(room_id)


def handle_correct_answer(room_id, sid, x, y):
    room = ROOMS[room_id]
    cell = room["grid"][x][y]
    cell["status"] = "owned"
    cell["owner"] = sid
    room["players"][sid]["pos"] = (x, y)

    if sid in room["active_questions"]:
        del room["active_questions"][sid]

    socketio.emit("self_message", {"msg": "答對了，成功佔領此格！"}, room=sid)

    finish_player_if_stuck(room_id, sid)
    emit_room_state(room_id)
    try_end_game(room_id)


def start_timeout_checker():
    def loop():
        while True:
            now = time.time()
            for room_id, room in list(ROOMS.items()):
                expired = []
                for sid, q in list(room["active_questions"].items()):
                    if now >= q["deadline"]:
                        expired.append((sid, q["x"], q["y"]))
                for sid, x, y in expired:
                    socketio.emit("question_timeout", {}, room=sid)
                    handle_wrong_or_timeout(room_id, sid, x, y, is_timeout=True)
            socketio.sleep(1)

    socketio.start_background_task(loop)


@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("join")
def on_join(data):
    room_id = data.get("room", "").strip()
    character = data.get("character", "slow")
    board_size = int(data.get("board_size", 3))
    max_players = int(data.get("max_players", 2))

    if not room_id:
        emit("self_message", {"msg": "請先輸入房間號。"})
        return

    if character not in CHARACTERS:
        emit("self_message", {"msg": "角色選擇錯誤。"})
        return

    if board_size not in [3, 4, 5, 6]:
        emit("self_message", {"msg": "地圖大小錯誤。"})
        return

    if max_players not in [2, 3, 4]:
        emit("self_message", {"msg": "玩家數錯誤。"})
        return

    if room_id not in ROOMS:
        ROOMS[room_id] = {
            "grid": create_grid(board_size),
            "board_size": board_size,
            "max_players": max_players,
            "players": {},
            "player_order": [],
            "host_id": request.sid,
            "started": False,
            "game_over": False,
            "winner_text": "",
            "active_questions": {},
            "timeout_started": False,
        }

    room = ROOMS[room_id]

    if room["started"]:
        emit("self_message", {"msg": "此房間遊戲已開始，無法加入。"})
        return

    if len(room["players"]) >= room["max_players"] and request.sid not in room["players"]:
        emit("self_message", {"msg": "此房間已滿。"})
        return

    join_room(room_id)

    chosen_characters = [p["character"] for p in room["players"].values()]
    if character in chosen_characters and request.sid not in room["players"]:
        emit("self_message", {"msg": "此角色已被其他玩家選走。"})
        return

    if request.sid not in room["players"]:
        idx = len(room["players"])
        spawn_positions = get_spawn_positions(room["board_size"], room["max_players"])
        start_pos = spawn_positions[idx]
        colors = ["#e74c3c", "#3498db", "#2ecc71", "#f1c40f"]

        remove_two_count = 3 if character == "scholar" else 0
        force_occupy_count = 1 if character == "landlord" else 0

        room["players"][request.sid] = {
            "name": f"玩家{idx + 1}",
            "color": colors[idx],
            "pos": start_pos,
            "finished": False,
            "character": character,
            "skills": {
                "remove_two": remove_two_count,
                "reset_block": 1,
                "force_occupy": force_occupy_count,
            },
        }
        room["player_order"].append(request.sid)

    if not room["timeout_started"]:
        room["timeout_started"] = True
        start_timeout_checker()

    emit("joined", {"sid": request.sid, "room": room_id})
    emit_room_state(room_id)
    socketio.emit("system_message", {"msg": f"{room['players'][request.sid]['name']} 已加入大廳。"}, room=room_id)


@socketio.on("start_game")
def start_game(data):
    room_id = data["room"]
    if room_id not in ROOMS:
        return
    room = ROOMS[room_id]

    if request.sid != room["host_id"]:
        emit("self_message", {"msg": "只有房主可以開始遊戲。"})
        return

    if len(room["players"]) < 2:
        emit("self_message", {"msg": "至少需要 2 位玩家才能開始。"})
        return

    room["started"] = True

    for sid, player in room["players"].items():
        x, y = player["pos"]
        room["grid"][x][y]["status"] = "owned"
        room["grid"][x][y]["owner"] = sid

    emit_room_state(room_id)
    socketio.emit("system_message", {"msg": "遊戲開始！"}, room=room_id)


@socketio.on("preview_cell")
def preview_cell(data):
    room_id = data["room"]
    x = int(data["x"])
    y = int(data["y"])

    if room_id not in ROOMS:
        return
    room = ROOMS[room_id]

    if not room["started"] or room["game_over"]:
        return
    if request.sid not in room["players"]:
        return

    player = room["players"][request.sid]
    if player["finished"]:
        emit("self_message", {"msg": "你已結束，無法再作答。"})
        return
    if request.sid in room["active_questions"]:
        emit("self_message", {"msg": "你有一題尚未作答。"})
        return

    if (x, y) not in get_adjacent_cells(player["pos"], room["board_size"]):
        emit("self_message", {"msg": "只能選擇上下左右鄰近格。"})
        return

    cell = room["grid"][x][y]
    if cell["status"] != "hidden":
        emit("self_message", {"msg": "該格不可挑戰。"})
        return

    emit(
        "cell_preview",
        {
            "x": x,
            "y": y,
            "type": cell["question"]["type"],
        },
        room=request.sid
    )


@socketio.on("start_answer")
def start_answer(data):
    room_id = data["room"]
    x = int(data["x"])
    y = int(data["y"])

    if room_id not in ROOMS:
        return
    room = ROOMS[room_id]

    if request.sid not in room["players"]:
        return
    if not room["started"]:
        return

    player = room["players"][request.sid]
    if player["finished"]:
        return
    if request.sid in room["active_questions"]:
        emit("self_message", {"msg": "你有一題尚未作答。"})
        return

    if (x, y) not in get_adjacent_cells(player["pos"], room["board_size"]):
        emit("self_message", {"msg": "只能作答鄰近格。"})
        return

    cell = room["grid"][x][y]
    if cell["status"] != "hidden":
        emit("self_message", {"msg": "該格不可作答。"})
        return

    q = copy.deepcopy(cell["question"])
    extra_time = 5 if player["character"] == "slow" else 0
    seconds = BASE_TIME_LIMIT + extra_time

    room["active_questions"][request.sid] = {
        "x": x,
        "y": y,
        "question": q,
        "deadline": time.time() + seconds,
        "used_remove_two": False,
    }

    emit(
        "question_started",
        {
            "x": x,
            "y": y,
            "type": q["type"],
            "q": q["q"],
            "options": q["options"],
            "seconds": seconds,
        },
        room=request.sid
    )


@socketio.on("submit_answer")
def submit_answer(data):
    room_id = data["room"]
    answer = data["answer"]

    if room_id not in ROOMS:
        return
    room = ROOMS[room_id]

    active = room["active_questions"].get(request.sid)
    if not active:
        emit("self_message", {"msg": "目前沒有進行中的題目。"})
        return

    if time.time() > active["deadline"]:
        handle_wrong_or_timeout(room_id, request.sid, active["x"], active["y"], is_timeout=True)
        return

    if answer == active["question"]["answer"]:
        handle_correct_answer(room_id, request.sid, active["x"], active["y"])
    else:
        handle_wrong_or_timeout(room_id, request.sid, active["x"], active["y"], is_timeout=False)


@socketio.on("use_remove_two")
def use_remove_two(data):
    room_id = data["room"]
    if room_id not in ROOMS:
        return

    room = ROOMS[room_id]
    if request.sid not in room["players"]:
        return

    player = room["players"][request.sid]
    active = room["active_questions"].get(request.sid)

    if not active:
        emit("self_message", {"msg": "目前沒有進行中的題目。"})
        return

    if player["skills"]["remove_two"] <= 0:
        emit("self_message", {"msg": "刪除兩個選項已用完。"})
        return

    if active["used_remove_two"]:
        emit("self_message", {"msg": "這題已用過刪除兩個選項。"})
        return

    correct = active["question"]["answer"]
    wrong_options = [opt for opt in active["question"]["options"] if opt != correct]
    remove_list = random.sample(wrong_options, 2)
    remain_options = [opt for opt in active["question"]["options"] if opt not in remove_list]
    random.shuffle(remain_options)

    player["skills"]["remove_two"] -= 1
    active["used_remove_two"] = True

    emit("options_reduced", {"options": remain_options}, room=request.sid)
    emit_room_state(room_id)


@socketio.on("use_reset_block")
def use_reset_block(data):
    room_id = data["room"]
    x = int(data["x"])
    y = int(data["y"])

    if room_id not in ROOMS:
        return
    room = ROOMS[room_id]

    if request.sid not in room["players"]:
        return

    player = room["players"][request.sid]
    if player["skills"]["reset_block"] <= 0:
        emit("self_message", {"msg": "重置灰格已用完。"})
        return

    if (x, y) not in get_adjacent_cells(player["pos"], room["board_size"]):
        emit("self_message", {"msg": "只能重置鄰近灰色格。"})
        return

    cell = room["grid"][x][y]
    if cell["status"] != "blocked":
        emit("self_message", {"msg": "這格不是灰色格。"})
        return

    cell["status"] = "hidden"
    cell["owner"] = None
    cell["question"] = weighted_question()
    player["skills"]["reset_block"] -= 1

    emit("self_message", {"msg": "成功重置一格灰色格。"}, room=request.sid)
    emit_room_state(room_id)


@socketio.on("use_force_occupy")
def use_force_occupy(data):
    room_id = data["room"]
    x = int(data["x"])
    y = int(data["y"])

    if room_id not in ROOMS:
        return
    room = ROOMS[room_id]

    if request.sid not in room["players"]:
        return

    player = room["players"][request.sid]
    if player["character"] != "landlord":
        emit("self_message", {"msg": "你不是霸道地主。"})
        return

    if player["skills"]["force_occupy"] <= 0:
        emit("self_message", {"msg": "強制霸佔已用完。"})
        return

    if (x, y) not in get_adjacent_cells(player["pos"], room["board_size"]):
        emit("self_message", {"msg": "只能霸佔鄰近隱藏格。"})
        return

    cell = room["grid"][x][y]
    if cell["status"] != "hidden":
        emit("self_message", {"msg": "只能霸佔隱藏格。"})
        return

    cell["status"] = "owned"
    cell["owner"] = request.sid
    player["pos"] = (x, y)
    player["skills"]["force_occupy"] -= 1

    emit("self_message", {"msg": "已使用霸道地主技能，成功霸佔一格。"}, room=request.sid)

    finish_player_if_stuck(room_id, request.sid)
    emit_room_state(room_id)
    try_end_game(room_id)


@socketio.on("disconnect")
def on_disconnect():
    for room_id, room in list(ROOMS.items()):
        if request.sid in room["players"]:
            player_name = room["players"][request.sid]["name"]

            if request.sid in room["active_questions"]:
                del room["active_questions"][request.sid]

            del room["players"][request.sid]

            if request.sid in room["player_order"]:
                room["player_order"].remove(request.sid)

            if room["host_id"] == request.sid and room["player_order"]:
                room["host_id"] = room["player_order"][0]

            socketio.emit("system_message", {"msg": f"{player_name} 已離線。"}, room=room_id)

            if len(room["players"]) == 0:
                del ROOMS[room_id]
            else:
                emit_room_state(room_id)
            break


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
