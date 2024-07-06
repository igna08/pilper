from itertools import product
import re
import openai
import os
import requests
from flask import Flask, request, jsonify, render_template, send_from_directory, session
from flask_cors import CORS
import spacy
from bs4 import BeautifulSoup


# Configuración inicial
openai.api_key = 'sk-proj-eOIp24JaVTg2WR0KzNiNT3BlbkFJta0I3yIu5LTL5ZHwsMu1'  # Asegúrate de configurar tu variable de entorno
app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['DEBUG'] = True

# Cargar el modelo de lenguaje en español
nlp = spacy.load("es_core_news_md")

# Configuración de tokens de acceso
access_token = 'EAANXw0zqBXEBOZBXI62LT4LGoKpyJmbvk4v3ZClf3qa1UpWjkv9lytaoay3Fn3GOIRIUbxgvCNocZBIESWstLYRSzwxvx36RvRSdbwAmuODpNXwRDXGlNWDIIkkdsqHjiUEjq1qIJTsVG0JAgxalEhq1AgobOJMEQHdMs0bshB2zNPLxXwat8KYeZBHclq3HbZBaTXzmK0KxtMDgeKbKFq2cyYrAZD'
verify_token = '12345'
phone_number_id = '316436791556875'
WEBHOOK_VERIFY_TOKEN= 12345
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
    send_whatsapp_message(user_id, response_text, products)

def handle_instagram_message(message):
    user_id = message['sender']['id']
    user_text = message['message']['text']
    response_text, products = process_user_input(user_text)
    send_instagram_message(user_id, products)

def handle_messenger_message(message):
    user_id = message['sender']['id']
    user_text = message['message']['text']
    response_text, products = process_user_input(user_text)
    send_messenger_message(user_id, products)

def send_whatsapp_message(user_id, text, products):
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
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
    requests.post(url, headers=headers, json=data)

def send_instagram_message(user_id, products):
    url = f"https://graph.facebook.com/v19.0/me/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
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
    requests.post(url, headers=headers, json=data)

def send_messenger_message(user_id, products):
    url = f"https://graph.facebook.com/v19.0/me/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
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
    requests.post(url, headers=headers, json=data)

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
        session['has_greeted'] = False  # Estado de saludo
    
    # Si es la primera interacción y el saludo no ha sido dado
    if not session['has_greeted']:
        session['messages'].append({"role": "system", "content": "Hello! How can I assist you today?""You are an assistant at Surcan, a Family company located in the heart of Apóstoles, city of Misiones with more than 40 years of experience in the construction field. Be kind and friendly.Somos una empresa Familiar ubicada en el corazón de Apóstoles, ciudadde Misiones con mas de 40 años de experiencia en el rubro de laconstrucción. Contamos con equipos capacitados y especializados endistintas áreas para poder asesorar a nuestros clientes de la mejormanera.Trabajamos con multiples marcas, Nacionales como Internacionales conun amplio espectro de categorías como Ferreteria, Pintureria, Sanitarios,Cocinas, Baños, Cerámicos y Guardas, Aberturas, Construcción en Seco,Siderúrgicos y otros.Visitanos o contactanos para contarnos sobre tus proyectos y poderelaborar un presupuesto en materiales realizado por nuestrosespecialistas en el tema.Abierto de lunes a viernes de 7:30hs a 12hs y 15hs a 19hs. Sábados de7:30hs a 12hs. Domingo CerradoINFORMACIÓN DE CONTACTO ADICIONAL03758 42-2637surcan.compras@gmail.comsurcan.ventas@gmail.comNormalmente respondemos en el transcurso del díaPolítica de privacidadSurcan S.A. asume la responsabilidad y obligación de las normas de laprivacidad respecto a todo tipo de transacción en sus sitios web y en lasdiferentes espacios y links que lo componen. Surcan SA tiene comoprincipal estandarte la protección de los datos personales de los usuariosy consumidores que accedan a sus plataformas informáticas, buscandoresguardar sus datos como así también evitar violaciones normativas seadentro de la ley de protección de datos personales, de la ley de defensadel consumidor, como en el manejo de dichos datos, evitar fraudes, estafas,sean estos de cualquier parte, incluso de terceros.En dicho contexto todo Usuario o Consumidor que voluntariamente accedaa las páginas Web de Surcan SA o cualquiera de sus plataformas vinculadasdeclaran conocer de manera expresa las presentes políticas de privacidad.De igual manera se comprometen a brindar sus datos, informacionespersonales y todo otro dato relativo a la operatoria o vinculación con lamisma de manera fidedigna y real y expresan y otorgan su consentimientoal uso por parte de SURCAN SA de dichos datos conforme se describe enesta Política de Privacidad. No obstante, en caso de tener consultas oinquietudes al respecto, no dude en contactarnos al siguientecorreo: surcan610@gmail.com.Política de reembolsoDocumentación a presentar para realizar elcambio• El cliente deberá presentar la documentación correspondiente deidentidad.• Sólo se realizarán devoluciones con el mismo método de pago dela compra.Estado del Producto• El producto no puede estar probado y/o usado (salvo en caso decambio por falla).• Debe tener su embalaje original (incluyendo interiores), Puedenestar abiertos, pero encontrarse en perfectas condiciones, (salvoaquellos productos que tienen envases sellados como Pinturas).• El producto debe estar completo, con todos sus accesorios,manuales, certificados de garantía correspondientes y con susproductos bonificados que hayan estado asociados a la compra.• No debe estar vencido.Cambio por Falla• En caso de devolución/cambio por falla, el producto debe haberseutilizado correctamente.• No se aceptarán devoluciones/cambios de constatarse mal uso delproducto.• Para herramientas eléctricas, se realizarán cambios directos dentrode las 72 hs de entregado el producto. En caso de haber pasado elplazo establecido, el cliente se debe contactar directamente con elservicio técnico oficial del producto.Plazos• Plazo Máximo: 15 días de corrido.• Productos con vencimiento: 7 días de corrido.• Los plazos para generar una devolución/cambio comienzan a correra partir del día de la entrega del producto.Política de envío.Zona de Envios y Tiempos de EntregaZonas de EnvioLas zonas cubiertas para envios de compras realizas a través de nuestro e -commerce esta limitada a Misiones y Corrientes. Los envios se realizaran através de Correo Argentino, Via Cargo, o nuestro servicio de Logísticaprivada, de acuerdo al tipo de producto, lo seleccionado y disponible almomento de realizar el check out.Tiempos de EntregaEl tiempo de entrega planificado será informado en el checkout deacuerdo al tipo de producto seleccionado. El mismo empezará a correr apartir de haberse hecho efectivo el pago. El tiempo de aprobación del pagovaría según el medio utilizado. Por último el tiempo de entrega variadependiendo de la zona en la que usted se encuentre y del tipo de envíoseleccionado.Información ImportanteEstamos trabajando de acuerdo a los protocolos de salud establecidos ypor razones de público conocimiento contamos con personal reducido.Los tiempos de atención y entrega podrían verse afectados. Hacemosnuestro mayor esfuerzo.INSTAGRAM: https://www.instagram.com/elijasurcan/Datos de ContactoTelefono: 03758 42-2637Consultas: surcan.ventas@gmail.com"})
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
