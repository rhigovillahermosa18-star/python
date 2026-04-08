import sys
sys.stdout = open("debug_out.txt", "w")
sys.stderr = sys.stdout

from dotenv import load_dotenv
load_dotenv()

from api.index import app, supabase, PRODUCT_IMGS, product_image

with app.app_context():
    products = supabase.table("products").select("*").execute().data or []
    print("=== Products in Supabase ===")
    for p in products:
        img_field = p.get("image", "")
        resolved = product_image(p)
        print(f"  name='{p['name']}' | image='{img_field}' | resolved='{resolved}'")
    print("\n=== PRODUCT_IMGS keys ===")
    for k, v in PRODUCT_IMGS.items():
        print(f"  '{k}' -> '{v}'")

sys.stdout.flush()
sys.stdout.close()
