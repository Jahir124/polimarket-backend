import os
from supabase import create_client, Client

# Capturamos las variables que pusiste en Render
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

# Iniciamos el cliente de Supabase
supabase: Client = create_client(url, key) if url and key else None

def upload_image_to_supabase(file_bytes, file_name, content_type):
    if not supabase:
        print("Error: Supabase no está configurado.")
        return None
    
    bucket_name = "products-images" # El nombre exacto de tu bucket
    
    try:
        # 1. Subir la imagen
        supabase.storage.from_(bucket_name).upload(
            path=file_name,
            file=file_bytes,
            file_options={"content_type": content_type}
        )
        # 2. Obtener la URL pública
        public_url = supabase.storage.from_(bucket_name).get_public_url(file_name)
        return public_url
    except Exception as e:
        print(f"Error subiendo a Supabase: {e}")
        raise e