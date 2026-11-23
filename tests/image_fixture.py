from io import BytesIO
from PIL import Image
b=BytesIO();Image.new('RGB',(640,360),(20,40,70)).save(b,format='JPEG');JPEG=b.getvalue()
