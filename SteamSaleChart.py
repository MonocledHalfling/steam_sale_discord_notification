import asyncio
import requests
import discord
from discord.ext import commands, tasks
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz

TOKEN = "TOKEN_HERE"
CHANNEL_ID = 1346137926513463297  # 🔹 메시지를 보낼 채널 ID 입력

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

KST = pytz.timezone("Asia/Seoul")
limit = 300

# SteamCharts에서 상위 300개 게임 가져오기
async def get_top_games():
    games = []
    page = 1

    while len(games) < limit:
        url = f'https://steamcharts.com/top/p.{page}'
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        for row in soup.find_all('tr')[1:]:  # 첫 번째 tr은 헤더라서 제외
            cols = row.find_all('td')
            if len(cols) < 2:
                continue

            app_id = cols[1].a['href'].split('/')[-1]
            game_name = cols[1].text.strip()
            games.append({'app_id': app_id, 'name': game_name})

            if len(games) >= limit:
                break

        print(f"📥 {len(games)}/{limit}개 게임 로드 완료...")
        page += 1
        await asyncio.sleep(1)

    return games

# Steam Store API에서 할인율 & 가격 가져오기
async def get_discount_info(app_id):
    store_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(store_url, headers=headers, timeout=5)
        data = response.json()

        if data is None or not isinstance(data, dict) or str(app_id) not in data:
            print(f"⚠ {app_id}의 API 응답이 올바르지 않음 (None 반환)")
            return 0, "N/A"

        app_data = data.get(str(app_id), {})
        if not app_data.get('success', False):
            print(f"⚠ {app_id}의 API 응답 실패 (success=False)")
            return 0, "N/A"

        price_info = app_data.get('data', {}).get('price_overview', {})
        discount = price_info.get('discount_percent', 0)
        price = price_info.get('final_formatted', "N/A")

        await asyncio.sleep(1.5)  # 🔹 요청 간격을 늘려 Rate Limit 방지
        return discount, price

    except requests.exceptions.RequestException as e:
        print(f"🚨 Steam Store API 오류 발생: {e}")
        return 0, "N/A"

def get_store_url(app_id):
    return f"https://store.steampowered.com/app/{app_id}"

# 할인 정보 수집 및 디스코드 전송
async def send_discount_games():
    await bot.change_presence(status=discord.Status.idle, activity=discord.Game("정보 수집"))
    print("🔄 할인 게임 데이터 업데이트 중...")

    top_games = await get_top_games()
    filtered_games = []
    count = 1

    for game in top_games:
        discount, price = await get_discount_info(game['app_id'])
        not_found = True
        if discount >= 20:
            not_found = False
            filtered_games.append({
                'name': game['name'],
                'discount': discount,
                'price': price,
                'url': get_store_url(game['app_id'])
            })
            print(f"{count}/{limit} : ✅ {game['name']} | 할인: {discount}% | 가격: {price}")

        if not_found:
            print(f"{count}/{limit} : X {game['name']} | 할인: {discount}% | 가격: {price}")

        count += 1

    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(CHANNEL_ID)
        except discord.errors.NotFound:
            print("🚨 채널을 찾을 수 없습니다. 채널 ID를 확인하세요.")
            return

    if not filtered_games:
        await channel.send("⛔ 현재 할인 중인 인기 게임이 없습니다.")
        return

    messages = []
    current_message = "**📌 할인 중인 인기 게임 리스트 (매일 오전 6시 갱신)**\n"

    for game in filtered_games:
        new_line = f"🎮 [{game['name']}](<{game['url']}>) - 할인 {game['discount']}% (가격 {game['price']})\n"

        if len(current_message) + len(new_line) > 2000:
            messages.append(current_message)  # 현재 메시지를 리스트에 저장
            current_message = ""  # 새 메시지 시작

        current_message += new_line  # 새 항목 추가

    if current_message:
        messages.append(current_message)  # 마지막 메시지 저장

    # 분할된 메시지 전송
    for msg in messages:
        await channel.send(msg)

    print("✅ 할인 게임 정보 전송 완료!")
    await bot.change_presence(status=discord.Status.online, activity=discord.Game("오전 6시까지 대기"))

@tasks.loop(hours=24)
async def scheduled_discount_check():
    now = datetime.now(KST)
    target_time = now.replace(hour=6, minute=0, second=0, microsecond=0)

    if now >= target_time:  # 이미 오전 6시가 지났다면 다음 날 실행
        target_time += timedelta(days=1)

    wait_time = (target_time - now).total_seconds()
    print(f"🕒 다음 실행까지 대기: {wait_time / 3600:.2f} 시간")
    await asyncio.sleep(wait_time)
    await send_discount_games()

@bot.event
async def on_ready():
    print(f"✅ 로그인 완료: {bot.user}")
    await bot.change_presence(activity=discord.Game("오전 6시까지 대기"))

    if not scheduled_discount_check.is_running():
        scheduled_discount_check.start()

bot.run(TOKEN)
