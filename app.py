from gc import get_count
import time
import uuid
from flask import Flask, request, jsonify, render_template, send_from_directory, session, make_response
from flask_cors import CORS
from openai import OpenAI
import os
import requests
from bs4 import BeautifulSoup
import spacy
import sqlite3
from datetime import datetime, timedelta
import psycopg2
from psycopg2 import sql


# Configuración inicial
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))



# Usar el asistente preexistente desde la variable de entorno
assistant_id = os.getenv("ASSISTANT_ID")

# Inicializar thread_id como None
thread_id = None
access_token = os.getenv('ACCESS_TOKEN')
verify_token = os.getenv('VERIFY_TOKEN')
phone_number_id = os.getenv('PHONE_NUMBER_ID')
WEBHOOK_VERIFY_TOKEN = os.getenv('WEBHOOK_VERIFY_TOKEN')
app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['DEBUG'] = True

# Cargar el modelo de lenguaje en español
nlp = spacy.load("es_core_news_md")
from itertools import product
import re
import openai
import os
import requests
from flask import Flask, request, jsonify, render_template, send_from_directory, session
from flask_cors import CORS
import spacy
from bs4 import BeautifulSoup
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql//anyway_1_0_user:HC54z8E3mOWWi8RYFOUQ6wBHfFLmVI0q@dpg-cq68clss1f4s73du9nk0-a/anyway_1_0')

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def get_counts():
    conn = get_db_connection()
    c = conn.cursor()
    today = datetime.now()

    # Obtener conteo diario
    c.execute('SELECT count FROM daily_counts WHERE date = %s', (today.strftime('%Y-%m-%d'),))
    daily_count_row = c.fetchone()
    daily_count = daily_count_row[0] if daily_count_row else 0

    # Obtener conteo mensual
    c.execute('SELECT count FROM monthly_counts WHERE year = %s AND month = %s', (today.year, today.month))
    monthly_count_row = c.fetchone()
    monthly_count = monthly_count_row[0] if monthly_count_row else 0

    conn.close()
    return daily_count, monthly_count

def reset_monthly_counts():
    conn = get_db_connection()
    c = conn.cursor()
    today = datetime.now()
    c.execute('DELETE FROM monthly_counts WHERE year = %s AND month = %s', (today.year, today.month))
    conn.commit()
    conn.close()

def increment_daily_count():
    conn = get_db_connection()
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute('INSERT INTO daily_counts (date, count) VALUES (%s, 1) ON CONFLICT (date) DO UPDATE SET count = daily_counts.count + 1', (today,))
    conn.commit()
    conn.close()

def increment_monthly_count():
    conn = get_db_connection()
    c = conn.cursor()
    today = datetime.now()
    c.execute('INSERT INTO monthly_counts (year, month, count) VALUES (%s, %s, 1) ON CONFLICT (year, month) DO UPDATE SET count = monthly_counts.count + 1', (today.year, today.month))
    conn.commit()
    conn.close()
@app.route("/")
def home():
    return render_template("index.html")

@app.route('/webhook', methods=['GET', 'POST', 'OPTIONS'])
def webhook():
    if request.method == 'OPTIONS':
        return '', 200  # Responder exitosamente a las solicitudes OPTIONS
    
    if request.method == 'GET':
        # Obtener los parámetros de la solicitud
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        # Verificar el token de verificación
        if mode == "subscribe" and token == verify_token:
            # Responder con el desafío de verificación
            return challenge, 200
        else:
            return "Verification token mismatch", 403

    elif request.method == 'POST':
        data = request.get_json()
        if 'object' in data:
            if data['object'] == 'whatsapp_business_account':
                for entry in data['entry']:
                    for change in entry['changes']:
                        if 'messages' in change['value']:
                            for message in change['value']['messages']:
                                handle_whatsapp_message(message)
            elif data['object'] == 'instagram':
                for entry in data['entry']:
                    for change in entry['changes']:
                        if 'messaging' in change['value']:
                            for message in change['value']['messaging']:
                                handle_instagram_message(message)
            elif data['object'] == 'page':
                for entry in data['entry']:
                    for messaging_event in entry['messaging']:
                        handle_messenger_message(messaging_event)
        return "Event received", 200

def handle_whatsapp_message(message):
    user_id = message['from']
    user_text = message['text']['body']
    response_text, products = process_user_input(user_text)
    if products:
        send_whatsapp_message(user_id, response_text, products)
    else:
        send_whatsapp_message(user_id, response_text)

def handle_instagram_message(message):
    user_id = message['sender']['id']
    user_text = message['message']['text']
    response_text, products = process_user_input(user_text)
    if products:
        send_instagram_message(user_id, response_text, products)
    else:
        send_instagram_message(user_id, response_text)

def handle_messenger_message(message):
    user_id = message['sender']['id']
    user_text = message['message']['text']
    response_text, products = process_user_input(user_text)
    if products:
        send_messenger_message(user_id, response_text, products)
    else:
        send_messenger_message(user_id, response_text)

def send_whatsapp_message(user_id, text, products=None):
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    if products:
        sections = [
            {
                "title": "Productos",
                "rows": [{"id": product['id'], "title": product['title'], "description": product['subtitle']} for product in products]
            }
        ]
        data = {
            "messaging_product": "whatsapp",
            "to": user_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": text},
                "action": {
                    "button": "Ver productos",
                    "sections": sections
                }
            }
        }
    else:
        data = {
            "messaging_product": "whatsapp",
            "to": user_id,
            "type": "text",
            "text": {"body": text}
        }
    requests.post(url, headers=headers, json=data)

def send_instagram_message(user_id, text, products=None):
    url = f"https://graph.facebook.com/v19.0/me/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    if products:
        elements = [
            {
                "title": product['title'],
                "subtitle": product['subtitle'],
                "image_url": product.get('image_url', 'default-image.jpg'),
                "buttons": [
                    {
                        "type": "web_url",
                        "url": product['url'],
                        "title": "Ver más"
                    }
                ]
            } for product in products
        ]
        data = {
            "recipient": {"id": user_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "generic",
                        "elements": elements
                    }
                }
            }
        }
    else:
        data = {
            "recipient": {"id": user_id},
            "message": {"text": text}
        }
    requests.post(url, headers=headers, json=data)

def send_messenger_message(user_id, text, products=None):
    url = f"https://graph.facebook.com/v19.0/me/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    if products:
        elements = [
            {
                "title": product['title'],
                "subtitle": product['subtitle'],
                "image_url": product.get('image_url', 'default-image.jpg'),
                "buttons": [
                    {
                        "type": "web_url",
                        "url": product['url'],
                        "title": "Ver más"
                    }
                ]
            } for product in products
        ]
        data = {
            "recipient": {"id": user_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "generic",
                        "elements": elements
                    }
                }
            }
        }
    else:
        data = {
            "recipient": {"id": user_id},
            "message": {"text": text}
        }
    requests.post(url, headers=headers, json=data)

def process_user_input(user_text):
    # Aquí va la lógica de procesamiento del texto del usuario
    response_text = "Este es un texto de respuesta"  # Reemplaza esto con tu lógica
    products = []  # Suponiendo que la lógica puede devolver una lista de productos o una lista vacía
    
    # Asegurarse de que siempre devolvemos dos valores
    return response_text, products


@app.route('/chat', methods=['POST'])
def chatbot():
    data = request.get_json()
    user_input = data.get('message')
    if user_input:
        response_data = process_user_input(user_input)
        return jsonify(response_data)
    return jsonify({'error': 'No message provided'}), 400




# # Procesar la entrada del usuario


# Procesar la entrada del usuario
def process_user_input(user_input):
    # Revisa si ya existe un thread_id en la sesión
    if 'thread_id' not in session:
        print("[DEBUG] No se encontró thread_id en la sesión. Creando uno nuevo...")
        new_thread = client.beta.threads.create()
        session['thread_id'] = new_thread.id
        print(f"[DEBUG] Nuevo thread_id creado: {session['thread_id']}")
    else:
        print(f"[DEBUG] thread_id existente encontrado en la sesión: {session['thread_id']}")

    thread_id = session['thread_id']

    # Envía la entrada del usuario al hilo existente
    print(f"[DEBUG] Enviando entrada del usuario al thread_id: {thread_id}")
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_input,
    )
    print(f"[DEBUG] Entrada del usuario enviada: {user_input}")

    # Ejecuta la conversación
    print("[DEBUG] Ejecutando conversación con el asistente...")
    run = client.beta.threads.runs.create(
        assistant_id=assistant_id,
        thread_id=thread_id
    )
    run_id = run.id
    print(f"[DEBUG] Run creado con run_id: {run_id}")

    # Espera a que la ejecución se complete
    while True:
        run = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run_id
        )
        print(f"[DEBUG] Verificando estado del run: {run.status}")
        if run.status == 'completed':
            print("[DEBUG] Ejecución completada.")
            break
        time.sleep(3)  # Espera 3 segundos antes de volver a verificar

    # Recupera los mensajes del hilo para obtener la respuesta del asistente
    print("[DEBUG] Recuperando mensajes del hilo...")
    output_messages = client.beta.threads.messages.list(
        thread_id=thread_id
    )

    # Depuración de todos los mensajes obtenidos
    print(f"[DEBUG] Mensajes recuperados: {output_messages.data}")

    # Usa el primer mensaje devuelto para la respuesta del asistente
    if output_messages.data:
        print(f"[DEBUG] Primer mensaje del asistente encontrado: {output_messages.data[0]}")
        assistant_response = output_messages.data[0].content[0].text.value
        print(f"[DEBUG] Respuesta del asistente: {assistant_response}")
    else:
        assistant_response = "Lo siento, no pude obtener una respuesta en este momento."
        print("[DEBUG] No se encontraron mensajes del asistente.")

    return assistant_response, []

def is_product_search_intent(user_input):
    # Analiza el texto del usuario
    doc = nlp(user_input.lower())
    # Busca patrones en la frase que indiquen una intención de búsqueda
    for token in doc:
        if token.lemma_ in ["buscar", "necesitar", "querer"] and token.pos_ == "VERB":
            return True
    return False

def extract_product_name(user_input):
    # Analiza el texto del usuario
    doc = nlp(user_input.lower())
    product_name = []
    is_searching = False
    for token in doc:
        # Detectar la frase de búsqueda
        if token.lemma_ in ["buscar", "necesitar", "querer"] and token.pos_ == "VERB":
            is_searching = True
        # Extraer sustantivos después del verbo de búsqueda
        if is_searching and token.pos_ in ["NOUN", "PROPN"]:
            product_name.append(token.text)
    return " ".join(product_name)

def search_product_on_surcansa(product_name):
    search_url = f'https://surcansa.com.ar/search?q={product_name}'
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        # Solicitar el contenido de la página
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()  # Lanza un error en caso de un código de estado HTTP no exitoso
        
        # Crear un objeto BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')

        # Encontrar todos los elementos de productos en la página
        product_elements = soup.find_all('li', class_='grid__item')

        # Extraer información de cada producto
        products = []
        base_url = "https://surcansa.com.ar"
        for product in product_elements:
            # Extraer imagen
            img_tag = product.find('img')
            img_url = img_tag['src'] if img_tag else 'No image'
            
            # Extraer nombre y enlace
            link_tag = product.find('a', class_='full-unstyled-link')
            product_name = link_tag.get_text(strip=True) if link_tag else 'No name'
            product_link = f"{base_url}{link_tag['href']}" if link_tag and link_tag['href'].startswith('/') else link_tag['href']

            # Extraer precio
            price_tag = product.find('span', class_='price-item--regular')
            price = price_tag.get_text(strip=True) if price_tag else 'No price'

            # Crear un diccionario para el producto
            product = {
                'titulo': product_name,
                'link': product_link,
                'imagen': img_url,
                'precio': price
            }
            products.append(product)
            
            # Imprimir los detalles del producto en la consola
            print(f"Producto: {product_name}, Precio: {price}, Enlace: {product_link}, Imagen: {img_url}")
        
        # Limitar a 5 productos
        if products:
            productos = products[:5]
            elements = []
            for producto in productos:
                elements.append({
                    "title": producto['titulo'],
                    "image_url": producto['imagen'],
                    "subtitle": producto['precio'],
                    "default_action": {
                        "type": "web_url",
                        "url": producto['link'],
                        "webview_height_ratio": "tall",
                    },
                    "buttons": [
                        {
                            "type": "web_url",
                            "url": producto['link'],
                            "title": "Ver Producto"
                        }
                    ]
                })
            return {"carousel": elements}
        else:
            return {"response": f"No encontré productos para '{product_name}'."}
    except Exception as e:
        return {"response": f"Ocurrió un error inesperado: {str(e)}"}



@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

@app.route('/reset', methods=['POST'])
def reset():
    session.pop('messages', None)
    return jsonify({'status': 'session reset'})

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", puerto=os.getenv("PORT", predeterminado=5000))
