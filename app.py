from itertools import product
import re
import openai
import os
import requests
from flask import Flask, request, jsonify, render_template, send_from_directory, session
from flask_cors import CORS
import spacy
from bs4 import BeautifulSoup
import psycopg2
from psycopg2 import sql


# Configuración inicial
openai.api_key = os.getenv('OPENAI_API_KEY')  # Asegúrate de configurar tu variable de entorno
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

def process_user_input(user_input):
    if 'messages' not in session:
        session['messages'] = []
        session['has_greeted'] = True  # Estado de saludo
    
    # Si es la primera interacción y el saludo no ha sido dado
    if not session['has_greeted']:
        session['messages'].append({"role": "system", "content": (
            "Cualquier pregunta especifica de un producto como precios, caracteristicas,variantes ,etc;responde al usuario que escriba el nombre del producto o Estoy buscando....., quiero un.... , necesito..... y que tu te pondras en acción para proveerle los mejores productos a su busqueda"
            "Hello! How can I assist you today?"
            "You are an assistant at Surcan, a Family company located in the heart of Apóstoles, city of Misiones with more than 40 years of experience in the construction field. "
            "Be kind and friendly. Somos una empresa Familiar ubicada en el corazón de Apóstoles, ciudad de Misiones con más de 40 años de experiencia en el rubro de la construcción. "
            "Contamos con equipos capacitados y especializados en distintas áreas para poder asesorar a nuestros clientes de la mejor manera. "
            "Trabajamos con múltiples marcas, Nacionales como Internacionales con un amplio espectro de categorías como Ferreteria, Pintureria, Sanitarios, Cocinas, Baños, Cerámicos y Guardas, Aberturas, Construcción en Seco, Siderúrgicos y otros. "
            "Visítanos o contáctanos para contarnos sobre tus proyectos y poder elaborar un presupuesto en materiales realizado por nuestros especialistas en el tema. "
            "Abierto de lunes a viernes de 7:30hs a 12hs y 15hs a 19hs. Sábados de 7:30hs a 12hs. Domingo Cerrado. "
            "INFORMACIÓN DE CONTACTO ADICIONAL: 03758 42-2637, surcan.compras@gmail.com, surcan.ventas@gmail.com "
            "Normalmente respondemos en el transcurso del día. "
            "Política de privacidad: Surcan S.A. asume la responsabilidad y obligación de las normas de la privacidad respecto a todo tipo de transacción en sus sitios web y en las diferentes espacios y links que lo componen. "
            "Surcan SA tiene como principal estandarte la protección de los datos personales de los usuarios y consumidores que accedan a sus plataformas informáticas, buscando resguardar sus datos como así también evitar violaciones normativas sea dentro de la ley de protección de datos personales, de la ley de defensa del consumidor, como en el manejo de dichos datos, evitar fraudes, estafas, sean estos de cualquier parte, incluso de terceros. "
            "En dicho contexto todo Usuario o Consumidor que voluntariamente acceda a las páginas Web de Surcan SA o cualquiera de sus plataformas vinculadas declaran conocer de manera expresa las presentes políticas de privacidad. "
            "De igual manera se comprometen a brindar sus datos, informaciones personales y todo otro dato relativo a la operatoria o vinculación con la misma de manera fidedigna y real y expresan y otorgan su consentimiento al uso por parte de SURCAN SA de dichos datos conforme se describe en esta Política de Privacidad. "
            "No obstante, en caso de tener consultas o inquietudes al respecto, no dude en contactarnos al siguiente correo: surcan610@gmail.com. "
            "Política de reembolso: Documentación a presentar para realizar el cambio: El cliente deberá presentar la documentación correspondiente de identidad. Sólo se realizarán devoluciones con el mismo método de pago de la compra. "
            "Estado del Producto: El producto no puede estar probado y/o usado (salvo en caso de cambio por falla). Debe tener su embalaje original (incluyendo interiores), Pueden estar abiertos, pero encontrarse en perfectas condiciones, (salvo aquellos productos que tienen envases sellados como Pinturas). "
            "El producto debe estar completo, con todos sus accesorios, manuales, certificados de garantía correspondientes y con sus productos bonificados que hayan estado asociados a la compra. No debe estar vencido. "
            "Cambio por Falla: En caso de devolución/cambio por falla, el producto debe haberse utilizado correctamente. No se aceptarán devoluciones/cambios de constatarse mal uso del producto. "
            "Para herramientas eléctricas, se realizarán cambios directos dentro de las 72 hs de entregado el producto. En caso de haber pasado el plazo establecido, el cliente se debe contactar directamente con el servicio técnico oficial del producto. "
            "Plazos: Plazo Máximo: 15 días de corrido. Productos con vencimiento: 7 días de corrido. Los plazos para generar una devolución/cambio comienzan a correr a partir del día de la entrega del producto. "
            "Política de envío. Zona de Envios y Tiempos de Entrega Zonas de Envio: Las zonas cubiertas para envios de compras realizas a través de nuestro e -commerce esta limitada a Misiones y Corrientes. "
            "Los envios se realizaran através de Correo Argentino, Via Cargo, o nuestro servicio de Logística privada, de acuerdo al tipo de producto, lo seleccionado y disponible al momento de realizar el check out. "
            "Tiempos de Entrega: El tiempo de entrega planificado será informado en el checkout de acuerdo al tipo de producto seleccionado. El mismo empezará a correr a partir de haberse hecho efectivo el pago. "
            "El tiempo de aprobación del pago varía según el medio utilizado. Por último el tiempo de entrega varía dependiendo de la zona en la que usted se encuentre y del tipo de envío seleccionado. "
            "Información Importante: Estamos trabajando de acuerdo a los protocolos de salud establecidos y por razones de público conocimiento contamos con personal reducido. Los tiempos de atención y entrega podrían verse afectados. Hacemos nuestro mayor esfuerzo. "
            "INSTAGRAM: https://www.instagram.com/elijasurcan/ "
            "Datos de Contacto: Teléfono: 03758 42-2637, Consultas: surcan.ventas@gmail.com"
        )})
        session['has_greeted'] = True  # Marcar que se ha saludado
    
    session['messages'].append({"role": "user", "content": user_input})
    
    try:
        if is_product_search_intent(user_input):
            product_name = extract_product_name(user_input)
            bot_message = search_product_on_surcansa(product_name)
        else:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo-0125",
                messages=session['messages'],
                temperature=0.01  # Ajusta la temperatura aquí
            )
            bot_message = {"response": response.choices[0].message['content'].strip()}
            session['messages'].append({"role": "assistant", "content": bot_message['response']})
        
        return bot_message
    except Exception as e:
        print(f"Error processing input: {str(e)}")
        return {"response": "Lo siento, hubo un problema al procesar tu solicitud."}

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
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()  # Raises an HTTPError for bad status codes

        soup = BeautifulSoup(response.text, 'html.parser')
        productos = []
        
        for item in soup.select('.card__content'):
            titulo_elem = item.select_one('.card__heading a')
            precio_elem = item.select_one('.price-item--regular')
            if titulo_elem and precio_elem:
                titulo = titulo_elem.get_text(strip=True)
                precio = precio_elem.get_text(strip=True)
                link = 'https://surcansa.com.ar' + titulo_elem['href']
                
                # Extraer la URL de la imagen principal del producto
                img_elem = item.select_one('img[src]')
                if img_elem:
                    img_src = img_elem['src']
                    # Asegurarse de que la URL de la imagen sea completa
                    if not img_src.startswith('http'):
                        img_src = 'https:' + img_src
                    # Añadir el parámetro 'width=150' para ajustar el tamaño de la imagen
                    img_url = f"http:{img_src.split('?')[0]}?width=150"
                else:
                    img_url = "https://via.placeholder.com/150"  # Imagen predeterminada
                
                productos.append({
                    'titulo': titulo,
                    'precio': precio,
                    'link': link,
                    'imagen': img_url
                })
        
        if productos:
            productos = productos[:5]  # Limitar a 5 productos
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
    
    except requests.RequestException as e:
        return {"response": f"Error al buscar productos: {e}"}

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
