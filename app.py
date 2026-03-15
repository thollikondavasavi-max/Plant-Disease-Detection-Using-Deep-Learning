from flask import Flask, request, render_template, jsonify, session, send_file
import os
import base64
import json
from groq import Groq
from PIL import Image, ImageEnhance
import io
from dotenv import load_dotenv
from datetime import datetime
import uuid

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management

# Initialize Groq client
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is required. Please set it in your .env file or environment.")

groq_client = Groq(api_key=GROQ_API_KEY)

# Store reports in memory (in production, use a database)
reports_storage = {}

def encode_image_to_base64(image_file):
    """Convert uploaded image to base64 for AI analysis"""
    try:
        # Reset file pointer to beginning
        image_file.seek(0)
        
        # Open and process the image
        image = Image.open(image_file)
        
        # Convert to RGB if necessary (handles PNG with transparency, etc.)
        if image.mode in ('RGBA', 'LA', 'P'):
            # Create white background for transparent images
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Resize if too large (optimal size for vision models)
        max_size = 1024
        if image.width > max_size or image.height > max_size:
            # Calculate new size maintaining aspect ratio
            ratio = min(max_size / image.width, max_size / image.height)
            new_size = (int(image.width * ratio), int(image.height * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        
        # Enhance image quality for better analysis
        from PIL import ImageEnhance
        
        # Slightly enhance contrast and sharpness
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.1)
        
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.1)
        
        # Convert to base64
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=90, optimize=True)
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        print(f"Image processed successfully: {len(image_base64)} bytes")  # Debug logging
        return image_base64
        
    except Exception as e:
        print(f"Error processing image: {e}")
        return None

def analyze_plant_image(image_base64):
    """Analyze plant image using multiple approaches for better accuracy"""
    try:
        print("Starting intelligent plant image analysis...")
        
        # Validate base64 data
        if not image_base64 or image_base64 == "dummy_base64":
            return create_fallback_analysis("No valid image data provided")
        
        # Decode and analyze the actual image
        try:
            import base64
            from PIL import Image, ImageStat
            import io
            
            image_data = base64.b64decode(image_base64)
            image = Image.open(io.BytesIO(image_data))
            
            # Analyze image characteristics
            image_analysis = analyze_image_characteristics(image)
            print(f"Image analysis complete: {image_analysis}")
            
        except Exception as decode_error:
            print(f"Image decoding error: {decode_error}")
            return create_fallback_analysis("Image decoding failed")
        
        # Generate AI analysis based on image characteristics
        analysis_prompt = f"""You are an expert plant pathologist. Based on the following image analysis data, provide a detailed plant diagnosis:

Image Analysis Data:
- Dominant colors: {image_analysis['dominant_colors']}
- Image brightness: {image_analysis['brightness']}
- Color distribution: {image_analysis['color_stats']}
- Image size: {image_analysis['size']}

Based on these visual characteristics, analyze what type of plant this might be and what conditions it might have:

ANALYSIS GUIDELINES:
1. If predominantly green colors with good brightness → likely healthy plant
2. If brown/yellow dominant colors → nutrient deficiency or disease
3. If white/gray areas → possible fungal infections (powdery mildew)
4. If dark spots → bacterial or fungal diseases
5. Consider plant type based on color patterns

Provide a JSON response with specific analysis based on these image characteristics:

{{
    "condition": "Based on color analysis - Healthy/Diseased/Nutrient Deficiency/Fungal Infection",
    "disease": "Specific disease based on color patterns and characteristics",
    "confidence": "Confidence level based on visual analysis (e.g., 75% based on color patterns)",
    "symptoms": "Symptoms inferred from image color and pattern analysis",
    "causes": "Likely causes based on visual characteristics observed",
    "treatment": "Specific treatment recommendations for the identified condition",
    "prevention": "Prevention measures for the specific plant type and condition",
    "weather": "Weather considerations for treatment"
}}

Be specific and base your analysis on the actual image characteristics provided. Make it unique to these specific color patterns."""

        print("Making AI analysis based on image characteristics...")
        
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "user", "content": analysis_prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            
            response_text = response.choices[0].message.content.strip()
            print(f"AI analysis response: {response_text[:200]}...")
            
            # Parse the JSON response
            try:
                response_text = response_text.replace('```json', '').replace('```', '').strip()
                
                # Remove any text before the JSON
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}') + 1
                
                if start_idx != -1 and end_idx > start_idx:
                    json_str = response_text[start_idx:end_idx]
                    
                    # Clean up any extra text or formatting
                    json_str = json_str.replace('**JSON Response:**', '').strip()
                    
                    report = json.loads(json_str)
                    
                    # Validate and clean the report
                    required_fields = ["condition", "disease", "confidence", "symptoms", "causes", "treatment", "prevention", "weather"]
                    for field in required_fields:
                        if field not in report or not isinstance(report[field], str):
                            report[field] = "Not specified"
                    
                    # Add image analysis metadata
                    report["image_analysis"] = f"Analyzed image: {image_analysis['size']}, dominant colors: {', '.join(image_analysis['dominant_colors'][:3])}"
                    report["note"] = f"💡 Analysis based on image color patterns and characteristics. Dominant colors detected: {', '.join(image_analysis['dominant_colors'][:3])}. For more detailed diagnosis, describe specific symptoms in the chat below!"
                    
                    return report
                    
            except Exception as parse_error:
                print(f"JSON parsing failed: {parse_error}")
                print(f"Raw response: {response_text}")  # Debug the raw response
                
        except Exception as ai_error:
            print(f"AI analysis failed: {ai_error}")
        
        # Fallback with image-specific information
        return create_image_specific_analysis(image_analysis)
        
    except Exception as e:
        print(f"Error in image analysis: {e}")
        import traceback
        traceback.print_exc()
        
        return create_fallback_analysis(str(e))

def create_fallback_analysis(error_msg):
    """Create fallback analysis when image processing fails"""
    return {
        "condition": "Image Analysis Unavailable",
        "disease": "Unable to process image",
        "confidence": "N/A",
        "symptoms": f"Image processing error: {error_msg}",
        "causes": "Technical limitation in image processing",
        "treatment": "Please try uploading a clear, well-lit image of the plant leaves",
        "prevention": "Ensure good image quality: clear focus, good lighting, close-up of affected areas",
        "weather": "N/A",
        "note": "💬 For immediate help, describe your plant's symptoms in the chat below! Our AI expert can provide targeted advice based on your description."
    }

def analyze_image_characteristics(image):
    """Analyze image characteristics to infer plant condition"""
    try:
        from PIL import ImageStat
        
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Get image statistics
        stat = ImageStat.Stat(image)
        
        # Calculate dominant colors
        colors = image.getcolors(maxcolors=256*256*256)
        if colors:
            # Sort by frequency and get top colors
            colors.sort(key=lambda x: x[0], reverse=True)
            dominant_colors = []
            
            for count, color in colors[:5]:  # Top 5 colors
                r, g, b = color
                if r > 100 and g > 100 and b < 100:  # Yellowish
                    dominant_colors.append("yellow/brown")
                elif r > 150 and g < 100 and b < 100:  # Reddish/brown
                    dominant_colors.append("red/brown")
                elif r < 100 and g > 100 and b < 100:  # Green
                    dominant_colors.append("green")
                elif r > 200 and g > 200 and b > 200:  # White
                    dominant_colors.append("white")
                elif r < 50 and g < 50 and b < 50:  # Dark/black
                    dominant_colors.append("dark/black")
                else:
                    dominant_colors.append("mixed")
        else:
            dominant_colors = ["unknown"]
        
        # Calculate brightness
        brightness = sum(stat.mean) / 3
        
        return {
            "dominant_colors": dominant_colors,
            "brightness": "bright" if brightness > 128 else "dark",
            "color_stats": {
                "red_avg": round(stat.mean[0], 1),
                "green_avg": round(stat.mean[1], 1), 
                "blue_avg": round(stat.mean[2], 1)
            },
            "size": f"{image.width}x{image.height}"
        }
        
    except Exception as e:
        print(f"Error analyzing image characteristics: {e}")
        return {
            "dominant_colors": ["unknown"],
            "brightness": "unknown",
            "color_stats": {"red_avg": 0, "green_avg": 0, "blue_avg": 0},
            "size": "unknown"
        }

def create_image_specific_analysis(image_analysis):
    """Create analysis based on image characteristics"""
    dominant_colors = image_analysis['dominant_colors']
    brightness = image_analysis['brightness']
    
    # Determine condition based on colors
    if "green" in dominant_colors and brightness == "bright":
        condition = "Likely Healthy"
        disease = "No obvious disease detected"
        symptoms = "Predominantly green coloration suggests healthy foliage"
        causes = "Good plant care and environmental conditions"
        treatment = "Continue current care routine, monitor regularly"
        
    elif "yellow/brown" in dominant_colors:
        condition = "Possible Nutrient Deficiency"
        disease = "Nitrogen or Iron deficiency suspected"
        symptoms = "Yellowing/browning of leaves detected in image analysis"
        causes = "Nutrient deficiency, overwatering, or natural aging"
        treatment = "Apply balanced fertilizer, check soil drainage, remove affected leaves"
        
    elif "white" in dominant_colors:
        condition = "Possible Fungal Infection"
        disease = "Powdery mildew or similar fungal condition"
        symptoms = "White coloration detected, possibly fungal growth"
        causes = "High humidity, poor air circulation, fungal spores"
        treatment = "Apply fungicide, improve ventilation, reduce humidity"
        
    elif "dark/black" in dominant_colors:
        condition = "Possible Disease"
        disease = "Bacterial or severe fungal infection"
        symptoms = "Dark spots or areas detected in image"
        causes = "Bacterial infection, severe fungal disease, or pest damage"
        treatment = "Remove affected areas, apply appropriate treatment, improve care conditions"
        
    else:
        condition = "Requires Further Analysis"
        disease = "Multiple factors possible"
        symptoms = "Mixed coloration patterns detected"
        causes = "Various factors could be involved"
        treatment = "Describe specific symptoms in chat for detailed diagnosis"
    
    return {
        "condition": condition,
        "disease": disease,
        "confidence": "Based on image color analysis",
        "symptoms": symptoms,
        "causes": causes,
        "treatment": treatment,
        "prevention": "Regular monitoring, proper watering, good air circulation, balanced nutrition",
        "weather": "Apply treatments during appropriate weather conditions",
        "image_analysis": f"Colors detected: {', '.join(dominant_colors[:3])}, brightness: {brightness}",
        "note": "💡 Analysis based on image color patterns. For species-specific advice, describe your plant type and symptoms in the chat!"
    }

def parse_text_response(text):
    """Parse non-JSON text response into structured format"""
    # Simple text parsing fallback
    lines = text.split('\n')
    
    # Try to extract key information from text
    condition = "Uncertain"
    disease = "Unable to determine"
    confidence = "N/A"
    
    # Look for key indicators in the text
    text_lower = text.lower()
    if any(word in text_lower for word in ['healthy', 'normal', 'good condition']):
        condition = "Healthy"
        disease = "None detected"
        confidence = "75%"
    elif any(word in text_lower for word in ['disease', 'infection', 'fungal', 'bacterial']):
        condition = "Diseased"
        confidence = "70%"
    elif any(word in text_lower for word in ['deficiency', 'nutrient', 'nitrogen', 'iron']):
        condition = "Nutrient Deficiency"
        confidence = "65%"
    
    return {
        "condition": condition,
        "disease": disease,
        "confidence": confidence,
        "symptoms": text[:150] + "..." if len(text) > 150 else text,
        "causes": "Based on visual analysis of the provided image",
        "treatment": "Consult with a local agricultural expert for specific treatment",
        "prevention": "Regular monitoring and proper plant care",
        "weather": "Consider weather conditions when applying treatments"
    }

def get_ai_chat_response(message):
    """Get AI response for plant care chat with enhanced diagnostic capabilities"""
    try:
        print(f"Chat request received: {message}")  # Debug log
        
        system_prompt = """You are Dr. PlantAI, an expert plant pathologist and botanist with 20+ years of experience in plant disease diagnosis and treatment. You have extensive knowledge of:

PLANT IDENTIFICATION:
- Leaf patterns, shapes, and arrangements for plant identification
- Common houseplants, garden plants, crops, and ornamental plants
- Regional plant varieties and their specific care needs

DISEASE EXPERTISE:
- Fungal diseases (powdery mildew, rust, blight, etc.)
- Bacterial infections (bacterial spot, canker, wilt, etc.)
- Viral diseases and their symptoms
- Nutrient deficiencies (N, P, K, Fe, Mg, etc.)
- Pest damage patterns (aphids, spider mites, thrips, etc.)
- Environmental stress symptoms

DIAGNOSTIC APPROACH:
1. First try to identify the plant type from user description
2. Ask specific questions about symptoms, location, care routine
3. Provide targeted diagnosis based on plant type and symptoms
4. Give specific treatment recommendations
5. Suggest prevention strategies

COMMUNICATION STYLE:
- Professional but friendly and approachable
- Ask follow-up questions to narrow down diagnosis
- Provide specific, actionable advice
- Use plant names and technical terms when appropriate
- Keep responses focused and under 250 words unless detailed explanation needed

When users describe symptoms, always try to:
1. Identify the plant species if possible
2. Ask about specific symptom details (color, location, progression)
3. Inquire about care routine (watering, light, fertilizer)
4. Consider environmental factors (humidity, temperature, season)
5. Provide targeted treatment for that specific plant type

If asked about non-plant topics, politely redirect to plant care."""

        print("Making API call to Groq...")  # Debug log
        
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            temperature=0.7,
            max_tokens=400
        )
        
        result = response.choices[0].message.content.strip()
        print(f"API response received: {result[:100]}...")  # Debug log
        return result
        
    except Exception as e:
        print(f"Error getting chat response: {e}")
        import traceback
        traceback.print_exc()
        return f"I'm having trouble connecting to the AI service right now. Error: {str(e)} Please try again in a moment. 🌱"

@app.route('/test-upload')
def test_upload():
    """Test page for image upload"""
    return """<!DOCTYPE html>
<html>
<head>
    <title>Test Image Upload</title>
</head>
<body>
    <h1>Test Plant Image Analysis</h1>
    <input type="file" id="fileInput" accept="image/*">
    <button onclick="testUpload()">Test Upload</button>
    <div id="result" style="border:1px solid #ccc; padding:10px; margin:10px 0; min-height:200px;"></div>

    <script>
        async function testUpload() {
            const fileInput = document.getElementById('fileInput');
            const result = document.getElementById('result');
            
            if (!fileInput.files.length) {
                alert('Please select a file first');
                return;
            }
            
            const formData = new FormData();
            formData.append('image', fileInput.files[0]);
            
            result.innerHTML = 'Uploading...';
            
            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    body: formData
                });
                
                console.log('Response status:', response.status);
                const data = await response.json();
                console.log('Response data:', data);
                
                if (data.status === 'success') {
                    const r = data.report;
                    result.innerHTML = `
                        <h3>Analysis Result:</h3>
                        <p><strong>Condition:</strong> ${r.condition}</p>
                        <p><strong>Disease:</strong> ${r.disease}</p>
                        <p><strong>Confidence:</strong> ${r.confidence}</p>
                        <p><strong>Symptoms:</strong> ${r.symptoms}</p>
                        <p><strong>Causes:</strong> ${r.causes}</p>
                        <p><strong>Treatment:</strong> ${r.treatment}</p>
                        <p><strong>Prevention:</strong> ${r.prevention}</p>
                        <p><strong>Weather:</strong> ${r.weather}</p>
                        ${r.note ? `<p><strong>Note:</strong> ${r.note}</p>` : ''}
                    `;
                } else {
                    result.innerHTML = `<p style="color:red;">Error: ${data.error}</p>`;
                }
                
            } catch (error) {
                console.error('Upload error:', error);
                result.innerHTML = `<p style="color:red;">Upload failed: ${error.message}</p>`;
            }
        }
    </script>
</body>
</html>"""

@app.route('/test-analyze')
def test_analyze():
    """Test endpoint to verify analyze function"""
    try:
        # Create a simple test image (green square to simulate healthy plant)
        from PIL import Image
        import io
        import base64
        
        # Create a test image with green color (simulating healthy plant)
        test_image = Image.new('RGB', (100, 100), color='green')
        buffer = io.BytesIO()
        test_image.save(buffer, format='JPEG')
        test_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        # Test the analyze function
        report = analyze_plant_image(test_base64)
        return jsonify({
            "status": "success",
            "report": report,
            "test_info": "Used green test image to simulate healthy plant"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/test-chat')
def test_chat():
    """Simple test page for chat functionality"""
    return """<!DOCTYPE html>
<html>
<head>
    <title>Test Chat</title>
</head>
<body>
    <h1>Test Plant AI Chat</h1>
    <div id="messages" style="border:1px solid #ccc; height:300px; overflow-y:scroll; padding:10px; margin:10px 0;"></div>
    <input type="text" id="messageInput" placeholder="Type your message..." style="width:300px; padding:5px;">
    <button onclick="sendMessage()" style="padding:5px 10px;">Send</button>

    <script>
        async function sendMessage() {
            const input = document.getElementById('messageInput');
            const messages = document.getElementById('messages');
            const message = input.value.trim();
            
            if (!message) return;
            
            // Show user message
            messages.innerHTML += `<div style="margin:5px 0;"><strong>You:</strong> ${message}</div>`;
            input.value = '';
            messages.scrollTop = messages.scrollHeight;
            
            try {
                console.log('Sending:', message);
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message })
                });
                
                console.log('Response status:', response.status);
                const data = await response.json();
                console.log('Response data:', data);
                
                // Show bot response
                messages.innerHTML += `<div style="margin:5px 0; background:#f0f0f0; padding:5px;"><strong>Bot:</strong> ${data.reply}</div>`;
                messages.scrollTop = messages.scrollHeight;
                
            } catch (error) {
                console.error('Error:', error);
                messages.innerHTML += `<div style="margin:5px 0; color:red;"><strong>Error:</strong> ${error.message}</div>`;
                messages.scrollTop = messages.scrollHeight;
            }
        }
        
        // Allow Enter key to send message
        document.getElementById('messageInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
    </script>
</body>
</html>"""

@app.route('/test-api')
def test_api():
    """Test endpoint to verify Groq API connectivity"""
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "Say 'API is working'"}],
            max_tokens=10
        )
        
        return jsonify({
            "status": "success",
            "response": response.choices[0].message.content,
            "model": "llama-3.1-8b-instant"
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/trynow')
def trynow():
    return render_template('trynow.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'image' not in request.files:
        return jsonify({"error": "No image provided"}), 400
    
    image_file = request.files['image']
    if image_file.filename == '':
        return jsonify({"error": "No image selected"}), 400
    
    # Check file type
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
    file_extension = image_file.filename.rsplit('.', 1)[1].lower() if '.' in image_file.filename else ''
    
    if file_extension not in allowed_extensions:
        return jsonify({"error": "Invalid file type. Please upload an image file."}), 400
    
    print(f"Processing image: {image_file.filename}, size: {len(image_file.read())} bytes")
    image_file.seek(0)  # Reset file pointer after reading size
    
    try:
        # Convert image to base64
        image_base64 = encode_image_to_base64(image_file)
        if not image_base64:
            return jsonify({"error": "Failed to process image. Please try a different image."}), 500
        
        print("Image encoded successfully, sending to AI...")
        
        # Analyze with AI
        report = analyze_plant_image(image_base64)
        
        # Generate unique report ID
        report_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get session ID (create if doesn't exist)
        if 'user_id' not in session:
            session['user_id'] = str(uuid.uuid4())
        
        user_id = session['user_id']
        
        # Store report
        if user_id not in reports_storage:
            reports_storage[user_id] = []
        
        report_data = {
            'id': report_id,
            'timestamp': timestamp,
            'report': report,
            'image': image_base64[:100] + '...',  # Store truncated for memory
            'title': f"Analysis - {report.get('condition', 'Unknown')} - {timestamp}"
        }
        
        reports_storage[user_id].append(report_data)
        
        print(f"Analysis complete: {report.get('condition', 'Unknown')}")
        
        return jsonify({
            "status": "success",
            "report": report,
            "report_id": report_id,
            "timestamp": timestamp
        })
        
    except Exception as e:
        print(f"Analysis error: {e}")
        return jsonify({
            "error": "Analysis failed. Please try again.",
            "details": str(e)
        }), 500

@app.route('/get-reports', methods=['GET'])
def get_reports():
    """Get all saved reports for the current user"""
    if 'user_id' not in session:
        return jsonify({"reports": []})
    
    user_id = session['user_id']
    user_reports = reports_storage.get(user_id, [])
    
    # Return simplified report list
    report_list = [{
        'id': r['id'],
        'timestamp': r['timestamp'],
        'title': r['title'],
        'condition': r['report'].get('condition', 'Unknown')
    } for r in user_reports]
    
    return jsonify({"reports": report_list})

@app.route('/get-report/<report_id>', methods=['GET'])
def get_report(report_id):
    """Get a specific report by ID"""
    if 'user_id' not in session:
        return jsonify({"error": "No session found"}), 404
    
    user_id = session['user_id']
    user_reports = reports_storage.get(user_id, [])
    
    for report in user_reports:
        if report['id'] == report_id:
            return jsonify({
                "status": "success",
                "report": report['report'],
                "timestamp": report['timestamp'],
                "title": report['title']
            })
    
    return jsonify({"error": "Report not found"}), 404

@app.route('/download-report/<report_id>/<format>', methods=['GET'])
def download_report(report_id, format):
    """Download report in specified format (txt, json, pdf)"""
    if 'user_id' not in session:
        return jsonify({"error": "No session found"}), 404
    
    user_id = session['user_id']
    user_reports = reports_storage.get(user_id, [])
    
    report_data = None
    for report in user_reports:
        if report['id'] == report_id:
            report_data = report
            break
    
    if not report_data:
        return jsonify({"error": "Report not found"}), 404
    
    r = report_data['report']
    timestamp = report_data['timestamp']
    
    if format == 'txt':
        content = f"""PLANT DISEASE ANALYSIS REPORT
Generated: {timestamp}

CONDITION: {r.get('condition', 'N/A')}
DISEASE: {r.get('disease', 'N/A')}
CONFIDENCE: {r.get('confidence', 'N/A')}

SYMPTOMS:
{r.get('symptoms', 'N/A')}

POSSIBLE CAUSES:
{r.get('causes', 'N/A')}

TREATMENT:
{r.get('treatment', 'N/A')}

PREVENTION:
{r.get('prevention', 'N/A')}

WEATHER SUGGESTION:
{r.get('weather', 'N/A')}

{r.get('note', '')}
"""
        return send_file(
            io.BytesIO(content.encode('utf-8')),
            mimetype='text/plain',
            as_attachment=True,
            download_name=f'plant_report_{timestamp.replace(":", "-")}.txt'
        )
    
    elif format == 'json':
        content = json.dumps({
            'timestamp': timestamp,
            'report': r
        }, indent=2)
        return send_file(
            io.BytesIO(content.encode('utf-8')),
            mimetype='application/json',
            as_attachment=True,
            download_name=f'plant_report_{timestamp.replace(":", "-")}.json'
        )
    
    else:
        return jsonify({"error": "Unsupported format"}), 400

@app.route('/delete-report/<report_id>', methods=['DELETE', 'POST'])
def delete_report(report_id):
    """Delete a specific report"""
    if 'user_id' not in session:
        return jsonify({"error": "No session found"}), 404
    
    user_id = session['user_id']
    user_reports = reports_storage.get(user_id, [])
    
    # Find and remove the report
    reports_storage[user_id] = [r for r in user_reports if r['id'] != report_id]
    
    return jsonify({"status": "success", "message": "Report deleted"})

@app.route('/chat', methods=['POST'])
def chat():
    try:
        print("Chat endpoint called")  # Debug log
        
        data = request.get_json()
        if not data or 'message' not in data:
            print("No message in request data")  # Debug log
            return jsonify({"error": "No message provided"}), 400
        
        message = data.get('message', '').strip()
        if not message:
            print("Empty message received")  # Debug log
            return jsonify({"error": "Empty message"}), 400
        
        print(f"Processing message: {message}")  # Debug log
        
        # Get AI response
        reply = get_ai_chat_response(message)
        
        print(f"Sending reply: {reply[:100]}...")  # Debug log
        
        return jsonify({"reply": reply})
        
    except Exception as e:
        print(f"Chat endpoint error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"reply": f"I'm experiencing technical difficulties. Error: {str(e)} Please try again. 🌱"}), 200

if __name__ == '__main__':
    print("Starting Plant AI with Groq AI Integration")
    print(" → http://127.0.0.1:5000")
    print(" → Make sure GROQ_API_KEY environment variable is set")
    app.run(debug=True, host='0.0.0.0', port=5000)