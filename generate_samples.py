import os
from PIL import Image, ImageDraw, ImageFont

def generate_sample_labels():
    sample_dir = os.path.join(os.path.dirname(__file__), 'sample_labels')
    os.makedirs(sample_dir, exist_ok=True)

    # Label 1: Clear label with Milk, Gluten, and May contain Peanuts
    img1 = Image.new('RGB', (800, 450), color=(255, 255, 255))
    d1 = ImageDraw.Draw(img1)
    
    label1_text = (
        "CHOCOLATE BISCUITS\n\n"
        "INGREDIENTS: Wheat flour, sugar, milk solids (12%),\n"
        "vegetable oil, cocoa powder, emulsifier (soya lecithin).\n\n"
        "CONTAINS: MILK, GLUTEN, SOY.\n\n"
        "MAY CONTAIN: Peanuts and tree nuts."
    )
    d1.text((40, 40), label1_text, fill=(0, 0, 0))
    img1.save(os.path.join(sample_dir, 'sample_milk_peanut_biscuit.png'))

    # Label 2: Label with Wheat, Soy, and Precautionary Egg
    img2 = Image.new('RGB', (800, 400), color=(248, 248, 248))
    d2 = ImageDraw.Draw(img2)
    
    label2_text = (
        "CRISPY POTATO CHIPS - SPICY FLAVOR\n\n"
        "INGREDIENTS: Dehydrated potatoes, refined wheat flour (maida),\n"
        "vegetable oil, seasoning, soya lecithin (E322), salt.\n\n"
        "CONTAINS: GLUTEN, SOY.\n\n"
        "Processed in a facility that also handles egg and fish."
    )
    d2.text((40, 40), label2_text, fill=(20, 20, 20))
    img2.save(os.path.join(sample_dir, 'sample_potato_chips.png'))

    # Label 3: Unreadable / Blurry low contrast image
    img3 = Image.new('RGB', (400, 200), color=(220, 220, 220))
    d3 = ImageDraw.Draw(img3)
    d3.text((30, 30), "x#... blurred unreadable label text ...", fill=(210, 210, 210))
    img3.save(os.path.join(sample_dir, 'sample_blurry_unreadable.png'))

    print("Sample labels generated successfully in sample_labels/")

if __name__ == '__main__':
    generate_sample_labels()
