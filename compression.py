import boto3
from flask import Flask, flash, request, redirect, url_for, render_template, jsonify
from werkzeug.utils import secure_filename
from PIL import Image
import fitz  # PyMuPDF
import os


app = Flask(__name__)

# AWS S3 configuration
s3_client = boto3.client('s3')
BUCKET_NAME = 'compress3'  # Replace with your S3 bucket name

app.secret_key = "secret key"
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Max file size (16 MB)

ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg', 'gif', 'pdf'])

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_pillow_format(file_type):
    format_map = {
        'jpg': 'JPEG',
        'jpeg': 'JPEG',
        'png': 'PNG',
        'pdf': 'PDF'
    }
    return format_map.get(file_type.lower(), 'JPEG')

def reduce_size_by_half(image_path, save_path, file_type):
    pillow_format = get_pillow_format(file_type)
    
    if file_type.lower() == 'pdf':
        pdf_document = fitz.open(image_path)
        pdf_page = pdf_document.load_page(0)
        pdf_image = pdf_page.get_pixmap()
        img = Image.frombytes("RGB", [pdf_image.width, pdf_image.height], pdf_image.samples)
        img.save(save_path, "PNG")
    else:
        img = Image.open(image_path)

    quality = 85
    initial_size = os.path.getsize(image_path)
    target_size = initial_size / 2

    while quality > 10:
        img.save(save_path, pillow_format, quality=quality, optimize=True)
        current_size = os.path.getsize(save_path)
        if current_size <= target_size:
            break
        quality -= 5

    return initial_size, current_size

@app.route('/home')
def home():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected for uploading'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        temp_file_path = os.path.join('/tmp', filename)

        # Save the file to a temporary location
        file.save(temp_file_path)

        # Upload the file to S3
        s3_client.upload_file(temp_file_path, BUCKET_NAME, filename)

        # Define the compressed file's name and path
        compressed_filename = f"{os.path.splitext(filename)[0]}_compressed{os.path.splitext(filename)[1]}"
        compressed_file_path = os.path.join('/tmp', compressed_filename)

        # Compress the file
        initial_size, compressed_size = reduce_size_by_half(temp_file_path, compressed_file_path, os.path.splitext(filename)[1].lower()[1:])

        # Upload the compressed file to S3
        s3_client.upload_file(compressed_file_path, BUCKET_NAME, compressed_filename)

        # Clean up temporary files
        os.remove(temp_file_path)
        os.remove(compressed_file_path)

        original_file_url = f'https://{BUCKET_NAME}.s3.amazonaws.com/{filename}'
        compressed_file_url = f'https://{BUCKET_NAME}.s3.amazonaws.com/{compressed_filename}'

        return jsonify({
            'message': 'File successfully uploaded and compressed',
            'original_file_url': original_file_url,
            'compressed_file_url': compressed_file_url,
            'initial_file_size': initial_size,
            'compressed_file_size': compressed_size
        }), 200
    else:
        return jsonify({'error': 'Allowed file types are - png, jpg, jpeg, gif, pdf'}), 400

@app.route('/display/<filename>')
def display_file(filename):
    s3_url = f'https://{BUCKET_NAME}.s3.amazonaws.com/{filename}'
    return jsonify({'file_url': s3_url}), 200

if __name__ == "__main__":
    app.run(debug=True)

