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
FREEZE_SECONDS = 5

timeout_checker_started = False

CHARACTERS = {
    "scholar": {
        "name": "學霸",
        "desc": "刪除兩個選項 3 次",
        "image": "/static/characters/scholar.png",
    },
    "landlord": {
        "name": "霸道地主",
        "desc": "可強制霸佔 1 格",
        "image": "/static/characters/landlord.png",
    },
    "seer": {
        "name": "先知",
        "desc": "可直接看見所有格子的題型",
        "image": "/static/characters/seer.png",
    },
    "time_master": {
        "name": "時間大師",
        "desc": "凍結其他所有玩家 5 秒作答時間",
        "image": "/static/characters/time_master.png",
    },
    "bomber": {
        "name": "炸彈怪客",
        "desc": "可炸毀任意 1 格使其變灰",
        "image": "/static/characters/bomber.png",
    },
}

DIFFICULTY_LABELS = {
    "normal": "普通題型",
    "hard": "困難題型",
    "extreme": "超級難題型",
    "mixed": "綜合題型",
}

def make_mcq(question, answer, wrongs, qtype):
    opts = [str(answer)] + [str(x) for x in wrongs[:3]]
    random.shuffle(opts)
    return {
        "type": qtype,
        "q": question,
        "options": opts,
        "answer": str(answer),
    }


def generate_normal_questions():
    qs = []

    for a in range(10, 40):
        for b in range(5, 15):
            ans = a + b
            qs.append(make_mcq(f"{a} + {b} = ?", ans, [ans - 1, ans + 1, ans + 2], "普通數學"))

    for a in range(20, 80, 2):
        for b in range(3, 10):
            ans = a - b
            qs.append(make_mcq(f"{a} - {b} = ?", ans, [ans - 2, ans + 1, ans + 3], "普通數學"))

    for a in range(2, 13):
        for b in range(2, 11):
            ans = a * b
            qs.append(make_mcq(f"{a} × {b} = ?", ans, [ans + 1, ans - 1, ans + a], "普通數學"))

    facts = [
        ("台灣首都是哪裡？", "台北", ["台中", "高雄", "台南"], "普通常識"),
        ("一年有幾個月？", "12", ["10", "11", "13"], "普通常識"),
        ("水的化學式是？", "H2O", ["CO2", "O2", "NaCl"], "普通科學"),
        ("電子帶什麼電？", "負電", ["正電", "中性", "不一定"], "普通科學"),
        ("Apple 的中文是？", "蘋果", ["香蕉", "葡萄", "鳳梨"], "普通英文"),
        ("Book 的中文是？", "書", ["筆", "桌子", "杯子"], "普通英文"),
        ("第二次世界大戰結束於哪一年？", "1945", ["1943", "1947", "1950"], "普通歷史"),
        ("2, 4, 8, 16, 下一個是？", "32", ["18", "24", "36"], "普通邏輯"),
        ("一週有幾天？", "7", ["5", "6", "8"], "普通常識"),
        ("1 公尺等於幾公分？", "100", ["10", "1000", "10000"], "普通常識"),
    ]

    for q, ans, wrongs, qtype in facts:
        for _ in range(16):
            qs.append(make_mcq(q, ans, wrongs, qtype))

    return qs[:240]


def generate_hard_questions():
    qs = []

    for base in range(100, 320, 10):
        pct = random.choice([10, 20, 25, 30, 40, 50])
        ans = int(base * pct / 100)
        qs.append(make_mcq(f"{base} 的 {pct}% 是多少？", ans, [ans + 5, max(1, ans - 5), ans + 10], "困難數學"))

    for x in range(2, 26):
        a = random.choice([2, 3, 4, 5, 6])
        b = random.choice([3, 4, 6, 8, 10, 12])
        ans = a * x + b
        qs.append(make_mcq(f"若 x = {x}，則 {a}x + {b} = ?", ans, [ans + 2, ans - 2, ans + 4], "困難數學"))

    for start in range(2, 20):
        diff = random.choice([2, 3, 4, 5, 6])
        seq = [start + i * diff for i in range(5)]
        ans = seq[-1] + diff
        qs.append(make_mcq(f"{seq[0]}, {seq[1]}, {seq[2]}, {seq[3]}, {seq[4]}, 下一個是？", ans, [ans - 1, ans + 1, ans + 2], "困難邏輯"))

    facts = [
        ("世界上面積最大的國家是？", "俄羅斯", ["中國", "美國", "加拿大"], "困難常識"),
        ("光速約為每秒多少公里？", "30萬", ["3萬", "300萬", "3億"], "困難常識"),
        ("DNA 雙螺旋結構由誰提出？", "華生與克里克", ["牛頓", "達爾文", "愛迪生"], "困難科學"),
        ("CPU 的主要功能是？", "運算與控制", ["儲存資料", "顯示畫面", "傳輸網路"], "困難觀念"),
        ("Break the ice 的意思是？", "破除尷尬", ["打破冰塊", "很冷", "生氣"], "困難英文"),
        ("Piece of cake 的意思是？", "很簡單", ["蛋糕一塊", "很困難", "很好吃"], "困難英文"),
        ("A 比 B 大，B 比 C 大，則？", "A 比 C 大", ["C 最大", "A 最小", "無法判斷"], "困難邏輯"),
        ("地球繞太陽一圈約多久？", "365", ["30", "180", "730"], "困難科學"),
    ]

    for q, ans, wrongs, qtype in facts:
        for _ in range(18):
            qs.append(make_mcq(q, ans, wrongs, qtype))

    return qs[:240]


def generate_extreme_questions():
    qs = []

    for x in range(2, 32):
        ans = 2 * (2 * x + 3) + 3
        qs.append(make_mcq(f"若 f(x)=2x+3，則 f(f({x})) = ?", ans, [ans - 2, ans + 2, ans + 5], "超難數學"))

    for a in range(50, 110, 3):
        b = random.choice([7, 9, 11, 13])
        ans = a % b
        qs.append(make_mcq(f"{a} ÷ {b} 的餘數是？", ans, [ans + 1, ans + 2, ans + 3], "超難數學"))

    binaries = [
        ("101101", 45),
        ("110010", 50),
        ("111111", 63),
        ("100101", 37),
        ("101011", 43),
        ("100111", 39),
        ("111001", 57),
    ]
    for bits, ans in binaries:
        for _ in range(12):
            qs.append(make_mcq(f"二進位 {bits} 轉十進位是？", ans, [ans - 1, ans + 1, ans + 2], "超難觀念"))

    facts = [
        ("哪個粒子不帶電？", "中子", ["電子", "質子", "離子"], "超難科學"),
        ("通貨膨脹最直接代表什麼？", "物價上升", ["股價下跌", "失業率下降", "貨幣消失"], "超難觀念"),
        ("若所有 A 都是 B，且沒有 B 是 C，則？", "沒有 A 是 C", ["有些 A 是 C", "所有 C 是 A", "無法判斷"], "超難邏輯"),
        ("1 到 100 中，能被 3 或 5 整除的數共有幾個？", "47", ["46", "48", "49"], "超難數學"),
        ("等差數列 3, 7, 11, ... 第 20 項為？", "79", ["75", "77", "81"], "超難數學"),
        ("某商品先漲 20% 再跌 20%，相較原價？", "少 4%", ["不變", "多 4%", "少 2%"], "超難觀念"),
        ("若今天是星期二，100 天後是星期幾？", "星期四", ["星期二", "星期三", "星期五"], "超難邏輯"),
    ]

    for q, ans, wrongs, qtype in facts:
        for _ in range(20):
            qs.append(make_mcq(q, ans, wrongs, qtype))

    return qs[:240]


QUESTION_POOLS = {
    "normal": generate_normal_questions(),
    "hard": generate_hard_questions(),
    "extreme": generate_extreme_questions(),
}
QUESTION_POOLS["mixed"] = (
    QUESTION_POOLS["normal"][:80]
    + QUESTION_POOLS["hard"][:80]
    + QUESTION_POOLS["extreme"][:80]
)

def pick_question(mode):
    return copy.deepcopy(random.choice(QUESTION_POOLS[mode]))


def create_grid(size, mode):
    return [[{
        "status": "hidden",
        "owner": None,
        "question": pick_question(mode)
    } for _ in range(size)] for _ in range(size)]


def get_spawn_positions(size, max_players):
    corners = [(0, 0), (0, size - 1), (size - 1, 0), (size - 1, size - 1)]
    return corners[:max_players]


def get_adjacent_cells(pos, size):
    x, y = pos
    candidates = [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
    return [(nx, ny) for nx, ny in candidates if 0 <= nx < size and 0 <= ny < size]


def count_owned_cells(room_id, sid):
    room = ROOMS[room_id]
    return sum(
        1 for row in room["grid"] for cell in row
        if cell["status"] == "owned" and cell["owner"] == sid
    )


def has_available_move(room_id, sid):
    room = ROOMS[room_id]
    if sid not in room["players"]:
        return False
    pos = room["players"][sid]["pos"]
    return any(
        room["grid"][nx][ny]["status"] == "hidden"
        for nx, ny in get_adjacent_cells(pos, room["board_size"])
    )


def finish_player_if_stuck(room_id, sid):
    room = ROOMS[room_id]
    if sid not in room["players"]:
        return
    player = room["players"][sid]
    if player["finished"] or sid in room["active_questions"]:
        return
    if not has_available_move(room_id, sid):
        player["finished"] = True
        socketio.emit("system_message", {
            "msg": f"{player['nickname']} 已無路可走，結束本局。"
        }, room=room_id)


def try_end_game(room_id):
    room = ROOMS[room_id]
    if room["game_over"] or len(room["players"]) < 2:
        return

    if all(p["finished"] for p in room["players"].values()):
        room["game_over"] = True
        ranking = [{
            "sid": sid,
            "name": p["nickname"],
            "count": count_owned_cells(room_id, sid),
            "color": p["color"],
            "character": p["character"],
            "character_name": CHARACTERS[p["character"]]["name"],
            "character_image": CHARACTERS[p["character"]]["image"],
        } for sid, p in room["players"].items()]

        ranking.sort(key=lambda x: x["count"], reverse=True)

        if len(ranking) >= 2 and ranking[0]["count"] == ranking[1]["count"]:
            room["winner_text"] = f"平手！最高皆為 {ranking[0]['count']} 格"
        else:
            room["winner_text"] = f"勝利者：{ranking[0]['name']}（{ranking[0]['character_name']}），共佔領 {ranking[0]['count']} 格"

        socketio.emit("game_over", {
            "winner_text": room["winner_text"],
            "ranking": ranking,
        }, room=room_id)


def personalized_room_state(room_id, sid):
    room = ROOMS[room_id]
    me = room["players"].get(sid)

    players_public = {}
    for psid, p in room["players"].items():
        players_public[psid] = {
            "name": p["name"],
            "nickname": p["nickname"],
            "color": p["color"],
            "pos": list(p["pos"]),
            "finished": p["finished"],
            "character": p["character"],
            "character_name": CHARACTERS[p["character"]]["name"],
            "character_image": CHARACTERS[p["character"]]["image"],
            "skills": p["skills"],
            "occupied_count": count_owned_cells(room_id, psid),
        }

    grid_public = []
    for row in room["grid"]:
        row_public = []
        for cell in row:
            c = {
                "status": cell["status"],
                "owner": cell["owner"],
                "type": None,
            }
            if me and me["character"] == "seer":
                c["type"] = cell["question"]["type"]
            row_public.append(c)
        grid_public.append(row_public)

    return {
        "room": room_id,
        "board_size": room["board_size"],
        "max_players": room["max_players"],
        "host_id": room["host_id"],
        "started": room["started"],
        "game_over": room["game_over"],
        "winner_text": room["winner_text"],
        "difficulty_mode": room["difficulty_mode"],
        "difficulty_label": DIFFICULTY_LABELS[room["difficulty_mode"]],
        "players": players_public,
        "grid": grid_public,
        "character_defs": CHARACTERS,
        "chosen_characters": [p["character"] for p in room["players"].values()],
    }


def emit_room_state(room_id):
    for sid in ROOMS[room_id]["players"]:
        socketio.emit("room_state", personalized_room_state(room_id, sid), room=sid)


def handle_wrong_or_timeout(room_id, sid, x, y, is_timeout=False):
    room = ROOMS[room_id]
    cell = room["grid"][x][y]
    cell["status"] = "blocked"
    cell["owner"] = None

    room["active_questions"].pop(sid, None)

    if sid in room["players"]:
        socketio.emit("self_message", {
            "msg": "超時，該格變灰。" if is_timeout else "答錯，該格變灰。"
        }, room=sid)

    finish_player_if_stuck(room_id, sid)
    emit_room_state(room_id)
    try_end_game(room_id)


def handle_correct_answer(room_id, sid, x, y):
    room = ROOMS[room_id]
    room["grid"][x][y]["status"] = "owned"
    room["grid"][x][y]["owner"] = sid
    room["players"][sid]["pos"] = (x, y)
    room["active_questions"].pop(sid, None)

    socketio.emit("self_message", {"msg": "答對了，成功佔領此格！"}, room=sid)
    finish_player_if_stuck(room_id, sid)
    emit_room_state(room_id)
    try_end_game(room_id)


def start_timeout_checker():
    global timeout_checker_started
    if timeout_checker_started:
        return
    timeout_checker_started = True

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
                    handle_wrong_or_timeout(room_id, sid, x, y, True)
            socketio.sleep(1)

    socketio.start_background_task(loop)

@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("join")
def on_join(data):
    room_id = data.get("room", "").strip()
    nickname = data.get("nickname", "").strip()
    character = data.get("character", "scholar")
    board_size = int(data.get("board_size", 3))
    max_players = int(data.get("max_players", 2))
    difficulty_mode = data.get("difficulty_mode", "mixed")

    if not room_id:
        emit("self_message", {"msg": "請先輸入房間號。"})
        return
    if not nickname:
        emit("self_message", {"msg": "請輸入暱稱。"})
        return
    if len(nickname) > 12:
        nickname = nickname[:12]
    if character not in CHARACTERS:
        emit("self_message", {"msg": "角色選擇錯誤。"})
        return
    if board_size not in [3, 4, 5, 6]:
        emit("self_message", {"msg": "地圖大小錯誤。"})
        return
    if max_players not in [2, 3, 4]:
        emit("self_message", {"msg": "玩家數錯誤。"})
        return
    if difficulty_mode not in DIFFICULTY_LABELS:
        emit("self_message", {"msg": "題庫模式錯誤。"})
        return

    if room_id not in ROOMS:
        ROOMS[room_id] = {
            "grid": create_grid(board_size, difficulty_mode),
            "board_size": board_size,
            "max_players": max_players,
            "difficulty_mode": difficulty_mode,
            "players": {},
            "player_order": [],
            "host_id": request.sid,
            "started": False,
            "game_over": False,
            "winner_text": "",
            "active_questions": {},
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
        start_pos = get_spawn_positions(room["board_size"], room["max_players"])[idx]
        colors = ["#e74c3c", "#3498db", "#2ecc71", "#f1c40f"]

        room["players"][request.sid] = {
            "name": f"玩家{idx + 1}",
            "nickname": nickname,
            "color": colors[idx],
            "pos": start_pos,
            "finished": False,
            "character": character,
            "skills": {
                "remove_two": 3 if character == "scholar" else 0,
                "reset_block": 1,
                "force_occupy": 1 if character == "landlord" else 0,
                "freeze_time": 1 if character == "time_master" else 0,
                "bomb_cell": 1 if character == "bomber" else 0,
            },
        }
        room["player_order"].append(request.sid)

    emit("joined", {"sid": request.sid, "room": room_id})
    emit_room_state(room_id)
    socketio.emit("system_message", {
        "msg": f"{room['players'][request.sid]['nickname']} 已加入大廳。"
    }, room=room_id)


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
    for sid, p in room["players"].items():
        x, y = p["pos"]
        room["grid"][x][y]["status"] = "owned"
        room["grid"][x][y]["owner"] = sid

    emit_room_state(room_id)
    socketio.emit("system_message", {
        "msg": f"遊戲開始！題庫模式：{DIFFICULTY_LABELS[room['difficulty_mode']]}"
    }, room=room_id)


@socketio.on("preview_cell")
def preview_cell(data):
    room_id = data["room"]
    x = int(data["x"])
    y = int(data["y"])

    if room_id not in ROOMS:
        return
    room = ROOMS[room_id]
    if not room["started"] or room["game_over"] or request.sid not in room["players"]:
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

    emit("cell_preview", {"x": x, "y": y, "type": cell["question"]["type"]}, room=request.sid)


@socketio.on("start_answer")
def start_answer(data):
    room_id = data["room"]
    x = int(data["x"])
    y = int(data["y"])

    if room_id not in ROOMS:
        return
    room = ROOMS[room_id]
    if request.sid not in room["players"] or not room["started"]:
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
    room["active_questions"][request.sid] = {
        "x": x,
        "y": y,
        "question": q,
        "deadline": time.time() + BASE_TIME_LIMIT,
        "used_remove_two": False,
    }

    emit("question_started", {
        "x": x,
        "y": y,
        "type": q["type"],
        "q": q["q"],
        "options": q["options"],
        "seconds": BASE_TIME_LIMIT,
    }, room=request.sid)

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
        handle_wrong_or_timeout(room_id, request.sid, active["x"], active["y"], True)
        return

    if answer == active["question"]["answer"]:
        handle_correct_answer(room_id, request.sid, active["x"], active["y"])
    else:
        handle_wrong_or_timeout(room_id, request.sid, active["x"], active["y"], False)


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
    cell["question"] = pick_question(room["difficulty_mode"])
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


@socketio.on("use_freeze_time")
def use_freeze_time(data):
    room_id = data["room"]
    if room_id not in ROOMS:
        return
    room = ROOMS[room_id]
    if request.sid not in room["players"]:
        return

    player = room["players"][request.sid]
    if player["character"] != "time_master":
        emit("self_message", {"msg": "你不是時間大師。"})
        return
    if player["skills"]["freeze_time"] <= 0:
        emit("self_message", {"msg": "凍結時間技能已用完。"})
        return

    player["skills"]["freeze_time"] -= 1
    affected = []

    for sid, active in room["active_questions"].items():
        if sid != request.sid:
            active["deadline"] += FREEZE_SECONDS
            affected.append(room["players"][sid]["nickname"])
            socketio.emit("freeze_effect", {"seconds": FREEZE_SECONDS}, room=sid)

    emit("self_message", {"msg": "你已使用時間凍結技能。"}, room=request.sid)
    socketio.emit("system_message", {
        "msg": f"{player['nickname']} 發動時間凍結" + (f"，影響：{', '.join(affected)}" if affected else "，但目前沒有人在作答")
    }, room=room_id)
    emit_room_state(room_id)


@socketio.on("use_bomb_cell")
def use_bomb_cell(data):
    room_id = data["room"]
    x = int(data["x"])
    y = int(data["y"])

    if room_id not in ROOMS:
        return
    room = ROOMS[room_id]
    if request.sid not in room["players"]:
        return

    player = room["players"][request.sid]
    if player["character"] != "bomber":
        emit("self_message", {"msg": "你不是炸彈怪客。"})
        return
    if player["skills"]["bomb_cell"] <= 0:
        emit("self_message", {"msg": "炸彈技能已用完。"})
        return
    if not (0 <= x < room["board_size"] and 0 <= y < room["board_size"]):
        emit("self_message", {"msg": "座標錯誤。"})
        return

    cell = room["grid"][x][y]
    if cell["status"] == "blocked":
        emit("self_message", {"msg": "這格已經是灰色格。"})
        return

    cell["status"] = "blocked"
    cell["owner"] = None
    player["skills"]["bomb_cell"] -= 1

    for sid in list(room["players"].keys()):
        finish_player_if_stuck(room_id, sid)

    emit("self_message", {"msg": f"你炸毀了 ({x}, {y})！"}, room=request.sid)
    socketio.emit("bomb_effect", {"x": x, "y": y}, room=room_id)
    emit_room_state(room_id)
    try_end_game(room_id)


@socketio.on("disconnect")
def on_disconnect():
    for room_id, room in list(ROOMS.items()):
        if request.sid in room["players"]:
            player_name = room["players"][request.sid]["nickname"]

            room["active_questions"].pop(request.sid, None)
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
    start_timeout_checker()
    socketio.run(app, host="0.0.0.0", port=5000)
