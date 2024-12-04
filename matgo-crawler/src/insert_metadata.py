# lib 
## selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC # expected_conditions (EC): Selenium에서 제공하는 여러 가지 조건을 정의한 모듈
from selenium.webdriver import ActionChains
from fake_useragent import UserAgent
## mongodb
from pymongo import MongoClient
from bson import json_util
## mysql
import mysql.connector
from mysql.connector import Error
## common
from urllib.parse import urlparse, urlunparse # url query 정리
import time
import re
import json
import random
import os
from dotenv import load_dotenv
import requests

## AI
from transformers import AutoModel, AutoProcessor
from PIL import Image
import torch

# .env 파일 불러오기
load_dotenv()

# 상수
## 크롤링
WAIT_TIMEOUT = random.uniform(10, 11) ## 대기 시간(초)
KEYWORD = "양천향교역 김치찌개" ## 테스트코드 맥도날드 명동점
URL = f"https://map.naver.com/restaurant/list?query={KEYWORD}" # https://pcmap.place.naver.com/place/list?query <-- 해당 url도 가능
## AI API KEY

## DB
mongo_ip = "127.0.0.1"
mongo_port = 40441
mongo_username = os.getenv("MONGO_DB_USERNAME")
mongo_pw = os.getenv("MONGO_DB_PW")
mongo_client_url = f"mongodb+srv://{mongo_username}:{mongo_pw}@cluster0.qehwj.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
# mysql_ip = "127.0.0.1"
# mysql_port = 46149
# mysql_admin = os.getenv("MYSQL_ADMIN")
# mysql_pw = os.getenv("MYSQL_PW")
# mysql_db_name = os.getenv("MYSQL_DB_NAME")

# 드라이버 실행 및 옵션 정의
ua = UserAgent(platforms="pc", browsers="chrome")
user_agents = ua.random
options = webdriver.ChromeOptions()
options.add_argument(f'--user-agent={user_agents}')
options.add_argument("--start-maximized")   # 화면 크게
options.add_experimental_option("detach", True) # 자동종료 방지(드라이버 유지)
#options.add_argument("--headless=chrome")
driver = webdriver.Chrome(options=options)
actions = ActionChains(driver)

# pymongo client 생성
client = MongoClient(mongo_client_url, tls=True, tlsAllowInvalidCertificates=True)

# AI 이미지 분석
model = AutoModel.from_pretrained("Bingsu/clip-vit-large-patch14-ko")
processor = AutoProcessor.from_pretrained("Bingsu/clip-vit-large-patch14-ko")


# 페이지 스크롤
def page_scroll(class_name):
    scroll_container = driver.find_element(By.CSS_SELECTOR, f".{class_name}")
    last_height = driver.execute_script("return arguments[0].scrollHeight", scroll_container) # execute_script = js 실행.

    while True:
            # 요소 내에서 아래로 3000px 스크롤
            driver.execute_script("arguments[0].scrollTop += 3000;", scroll_container)
            # 페이지 로드를 기다림
            time.sleep(random.uniform(1, 2))
            time.sleep(0.5)  # 동적 콘텐츠 로드 시간에 따라 조절
            # 스크롤 높이 계산
            new_height = driver.execute_script("return arguments[0].scrollHeight", scroll_container)

            # 스크롤이 더 이상 늘어나지 않으면 루프 종료
            if new_height == last_height:
                break
            last_height = new_height

# iframe 엘리먼트 지정
def focus_iframe(type):
    driver.switch_to.parent_frame()
    if type == 'list':
        iframe = driver.find_element(By.XPATH,'//*[@id="searchIframe"]')
    elif type == 'detail':
        wait = WebDriverWait(driver, WAIT_TIMEOUT)
        wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="entryIframe"]')))
        
        iframe = driver.find_element(By.XPATH,'//*[@id="entryIframe"]')
    driver.switch_to.frame(iframe)

# 위도 경도 좌표 구하는 탭 추가 후 값 return
def get_lat_lon(input_address):
    lat_lon_url = "https://gps.aply.biz/"
    driver.execute_script("window.open('');")
    time.sleep(1)

    wait = WebDriverWait(driver, 5)

    driver.switch_to.window(driver.window_handles[-1])  #새로 연 탭으로 이동
    driver.get(url=lat_lon_url)

    wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="gtco-header2"]/div/div[3]/div[2]/div[1]/input'))) # address input box 생성 대기
    address_box = driver.find_element(By.XPATH, '//*[@id="gtco-header2"]/div/div[3]/div[2]/div[1]/input')# 주소 인풋박스 div 찾기
    address_box.send_keys(input_address)

    driver.find_element(By.XPATH, '//*[@id="btnGetGpsByAddress"]').click()

    lat = driver.find_element(By.XPATH, '/html/body/div[3]/header/div/div[3]/div[1]/div[1]/input')
    lon = driver.find_element(By.XPATH, '/html/body/div[3]/header/div/div[3]/div[1]/div[2]/input')

    wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="askModal"]/div/div/div[2]'))) # 모달 생성 대기

    time.sleep(random.uniform(3, 4))


    lat_value = lat.get_attribute("value")
    lon_value = lon.get_attribute("value")

    time.sleep(random.uniform(1, 2))
    
    driver.close()
    driver.switch_to.window(driver.window_handles[0])

    return [lat_value, lon_value]

def extract_text_queries(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            # 파일에서 줄 단위로 읽기
            lines = file.readlines()
            # 각 줄에서 '|' 앞부분만 추출
            text_query = [line.split("|")[0].strip() for line in lines if "|" in line]
            return text_query
    except FileNotFoundError:
        raise ValueError(f"파일을 찾을 수 없습니다: {file_path}")
    except Exception as e:
        raise ValueError(f"에러 발생: {e}")

def ai_classification_food(url, text_query_file):
    if url != None:
        image = Image.open(requests.get(url, stream=True).raw)

        # 텍스트 쿼리 지정
        text_query = extract_text_queries(text_query_file)

        # 입력 데이터 준비
        inputs = processor(text=text_query, images=image, return_tensors="pt", padding=True)

        with torch.inference_mode():
            outputs = model(**inputs)

        # 이미지와 텍스트 간의 유사도 계산
        logits_per_image = outputs.logits_per_image
        probs = logits_per_image.softmax(dim=1)

        # 확률값에서 가장 큰 값을 찾음
        max_prob, pred_idx = torch.max(probs[0], dim=0)
        pred_text = text_query[pred_idx]

        # 조건에 따라 결과 반환
        if max_prob < 0.89:
            print("이미지 분석 취소: 신뢰도 높은 결과 없음")
            result = False
        else:
            print(f"이미지 분석 성공: {pred_text} (확률: {max_prob.item():.4f})")
            result = {"pred_text": pred_text, "probability": max_prob.item()}
            return result
    else:
        raise ValueError("이미지 url 확인에 실패했습니다.")

def check_category(classification_value):
    
    pass


def calc_famous_cnt(star, review):
    famous_cnt = star * 0.01 + review * 0.0002
    return famous_cnt

# img_list의 모든 URL에 대해 dict 리스트 구성
def detail_info():
    focus_iframe('detail')
    
    tab_list = driver.find_elements(By.CLASS_NAME, 'veBoZ')

    # 현재 URL 가져오기 및 처리
    current_url = driver.current_url
    parsed_url = urlparse(current_url)
    cleaned_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', '', ''))

    # 페이지 소스 가져와 BeautifulSoup로 파싱
    result_page = driver.page_source
    soup = BeautifulSoup(result_page, 'html.parser')
    
    detail_ele = soup.find('div', class_='PIbes')
    subject_ele = soup.find('div', class_='zD5Nm undefined')

    # 가게 상세 정보 추출
    # common
    url_path = urlparse(cleaned_url).path
    url_path_match = re.search(r'place/(\d+)', url_path)
    store_id = url_path_match.group(1) if url_path_match else None
    # mongo
    current_status = detail_ele.find('em').get_text() if detail_ele else None
    time_ele = soup.find('time', {'aria-hidden': 'true'}).get_text() if detail_ele else None
    strt_time, end_time = (time_ele, None) if current_status == '영업 종료' else (None, time_ele)
    # mysql
    store_nm = subject_ele.find('span', class_='GHAhO').get_text() if subject_ele else None
    address = detail_ele.find('span', class_='LDgIH').get_text() if detail_ele else None
    tel_no = detail_ele.find('span', class_='xlx7Q').get_text() if detail_ele else None
    star_rate = (subject_ele.find('span', class_='PXMot LXIwF').get_text() if subject_ele.find('span', class_='PXMot LXIwF') else "Node")
    category = subject_ele.find('span', class_='lnJFt').get_text() if subject_ele else None
    lat_lon_list = get_lat_lon(input_address=address)
    latitude = lat_lon_list[0]
    longitude = lat_lon_list[1]
    tags = ""

    # review_cn 연산
    visitor_review_txt = subject_ele.find('a', attrs={"href": f"/restaurant/{store_id}/review/visitor"}).get_text() if subject_ele else None
    blog_review_txt = subject_ele.find('a', attrs={"href": f"/restaurant/{store_id}/review/ugc"}).get_text() if subject_ele else None
    visitor_review_cn = re.search(r'\b\d{1,3}(?:,\d{3})*\b', visitor_review_txt).group()
    blog_review_cn = re.search(r'\b\d{1,3}(?:,\d{3})*\b', blog_review_txt).group()
    review_cn = int(visitor_review_cn.replace(',', '')) + int(blog_review_cn.replace(',', ''))

    # 이미지 리스트, 리뷰 리스트 수집
    focus_iframe("detail")
    WebDriverWait(driver, WAIT_TIMEOUT).until(EC.presence_of_element_located((By.CLASS_NAME, 'place_fixed_maintab')))
    WebDriverWait(driver, WAIT_TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, '.veBoZ')))

    img_list = []
    review_list = []
    tags_list = []

    for tab in tab_list:
        if tab.text == '리뷰':
            while True:
                try:
                    actions = ActionChains(driver)
                    actions.move_to_element_with_offset(tab, 5, 5).click().perform()

                    tab.click()
                    WebDriverWait(driver, WAIT_TIMEOUT).until(EC.presence_of_element_located((By.CLASS_NAME, 'pui__vn15t2')))
                    time.sleep(random.uniform(3, 4))
                    review_elems = driver.find_elements(By.CLASS_NAME, 'pui__vn15t2')

                    for review in review_elems:
                        review_text = review.text
                        cleaned_review_text = review_text.replace("\n", " ").replace("더보기","").strip()
                        review_list.append(cleaned_review_text)

                    tag_elems = driver.find_elements(By.CLASS_NAME,'pui__V8F9nN')

                    for tag in tag_elems:
                        tag_text = tag.text
                        tags_list.append(tag_text)
                    
                    tags = ",".join(tags_list)

                    time.sleep(0.5)
                    break
                except Exception as e:
                    try:
                        right_button = WebDriverWait(driver, WAIT_TIMEOUT).until(
                            EC.presence_of_element_located((By.CLASS_NAME, 'ZCqf_'))
                        )
                        span_tag = right_button.find_element(By.CLASS_NAME, 'nK_aH')
                        
                        actions = ActionChains(driver)
                        actions.move_to_element(span_tag).click().perform()

                        flicking_camera = WebDriverWait(driver, WAIT_TIMEOUT).until(
                            EC.presence_of_element_located((By.CLASS_NAME, 'flicking-camera'))
                        )
                        transform_style = flicking_camera.get_attribute('style')
                        print(f"Transform style: {transform_style}")

                        time.sleep(1)
                    except Exception as button_error:
                        print(f"리뷰 리스트 생성 실패: {button_error}")
        if tab.text == '사진':
            while True:
                try:
                    actions = ActionChains(driver)
                    actions.move_to_element_with_offset(tab, 5, 5).click().perform()

                    tab.click()
                    WebDriverWait(driver, WAIT_TIMEOUT).until(EC.presence_of_element_located((By.CLASS_NAME, 'wzrbN')))
                    time.sleep(random.uniform(2, 3))
                    img_elems = driver.find_elements(By.CLASS_NAME, 'wzrbN')
                    for img in img_elems:
                        img_url = img.find_element(By.XPATH, './/a/img').get_attribute('src')
                        is_img = ai_classification_food(url=img_url, text_query_file=)
                        if is_img != False:
                            img_list.append(img_url)
                    time.sleep(0.5)
                    break
                except Exception as e:
                    try:
                        right_button = WebDriverWait(driver, WAIT_TIMEOUT).until(
                            EC.presence_of_element_located((By.CLASS_NAME, 'ZCqf_'))
                        )
                        span_tag = right_button.find_element(By.CLASS_NAME, 'nK_aH')
                        
                        actions = ActionChains(driver)
                        actions.move_to_element(span_tag).click().perform()

                        flicking_camera = WebDriverWait(driver, WAIT_TIMEOUT).until(
                            EC.presence_of_element_located((By.CLASS_NAME, 'flicking-camera'))
                        )
                        transform_style = flicking_camera.get_attribute('style')
                        print(f"Transform style: {transform_style}")

                        time.sleep(1)
                    except Exception as button_error:
                        print(f"사진 리스트 생성 실패: {button_error}")

    image_meta_list = []
    store_information_list = []

    image_meta = {}
    store_information = {}

    for img_url in img_list:
        image_meta = {
            'store_id': store_id,
            'img_url': img_url,
            'tags': tags
        }
        time.sleep(0.2)
        image_meta_list.append(image_meta)
    
    store_information = {
        'store_id': store_id,
        'store_nm': store_nm,
        'address': address,
        'tel_no': tel_no,
        'review_cnt': review_cn,
        'star_rate': star_rate,
        'open_info': {
            'status': current_status,
            'start_time': strt_time,
            'end_time': end_time 
        },
        'location': {
            'type': 'Point',
            'coordinates': [latitude, longitude]
        },
        'category': category,
        'image_url': img_list,
        'naver_url': cleaned_url,
        'simple_review': review_list[0],
        'famous_cnt': calc_famous_cnt(star=star_rate, review=review_cn)
    }

    store_information_list.append(store_information)

    print("Image meta list 구성 완료:", image_meta_list)
    print("Detail info list 구성 완료:", store_information_list)
    return image_meta_list, store_information_list

# MongoDB에 데이터 삽입 함수
def conn_mongodb(detail_info_list):
    db = client.matgo  # 'matgo'라는 MongoDB 데이터베이스 선택
    try:
        db.metadata.insert_many(detail_info_list)  # 리스트를 insert_many로 삽입
        print("\n", "데이터가 MongoDB에 성공적으로 삽입되었습니다.", detail_info_list, "\n")
    except Exception as e:
        print("MongoDB에 데이터 삽입 중 오류 발생:", e)

# def conn_mysql():
#     connection = None
#     try:
#         connection = mysql.connector.connect(
#             host=mysql_ip,
#             port=mysql_port,
#             user=mysql_admin,
#             passwd=mysql_pw,
#             database=mysql_db_name
#         )
#         print("MySQL 데이터베이스에 연결됨.")
#     except Error as e:
#         print(f"MySQL 데이터베이스 연결 오류 발생: '{e}'")
#     return connection

# def insert_mysql(connection, detail_info_list):
#     cursor = connection.cursor()
#     insert_query = """
#     INSERT INTO store_information (store_id, store_nm, address, tel_no, review_cnt, star_rate, latitude, longitude, img_url, category, naver_url) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
#     """
#     try:
#         for detail_info in detail_info_list:
#             img_url_str = ", ".join(detail_info['img_url'])

#             tuple_detail_info = (
#                 detail_info['store_id'],
#                 detail_info['store_nm'],
#                 detail_info['address'],
#                 detail_info['tel_no'],
#                 detail_info['review_cnt'],
#                 detail_info['star_rate'],
#                 detail_info['latitude'],
#                 detail_info['longitude'],
#                 img_url_str,
#                 detail_info['category'],
#                 detail_info['naver_url']
#             )
#             cursor.execute(insert_query, tuple_detail_info)
#         connection.commit()  # 변경 사항 커밋
#         print("데이터가 MySQL에 성공적으로 삽입되었습니다.")
#     except Error as e:
#         print(f"MySQL에 데이터 삽입 중 오류 발생: \n '{e}'")
#     finally:
#         cursor.close()

# 크롤링 시작 함수
def crwl_data():
    driver.get(url=URL)
    try:
        time.sleep(random.uniform(1, 2))
        WebDriverWait(driver, WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, '//*[@id="section_content"]/div')))
        driver.find_element(By.XPATH, '//*[@id="searchIframe"]')
        focus_iframe('list')
        page_scroll("Ryr1F")
        
        store_list = driver.find_elements(By.CLASS_NAME, 'TYaxT')

        for index, store in enumerate(store_list, start=1):
            driver.switch_to.parent_frame()

            WebDriverWait(driver, WAIT_TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".SEARCH_MARKER > div")))
            
            focus_iframe('list')

            actions.click(store).perform()

            deatil_info_list = detail_info()

            # DB에 들어갈 json 데이터 생성
            image_meta_list = deatil_info_list[0]
            store_information_list = deatil_info_list[1]
            
            # 상세 정보 크롤링 및 mongo DB에 저장
            conn_mongodb(image_meta_list)
            conn_mongodb(store_information_list)

            # # 상세 정보 크롤링 및 mysql DB에 저장
            # mysql_connection = conn_mysql()
            # insert_mysql(mysql_connection, store_information_list)

            # if mysql_connection:
            #     mysql_connection.close()  # MySQL 연결 종료

            # 가게 5개로 임시 제한
            if index == 5:
                break
    except Exception as e:
        print("크롤링 작업이 실패했습니다:", e)

# test
try:
    crwl_data()
finally:
    driver.close()


