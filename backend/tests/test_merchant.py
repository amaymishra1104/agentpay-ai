import os
os.environ["DATABASE_URL"] = "sqlite:///./agentpay.db"

import pytest
from app.services import cart_service
from app.db.database import SessionLocal, init_db
from app.services.catalog_service import _load_products, _load_merchants

def test_merchant_validation_and_mismatch():
    init_db()
    db_session = SessionLocal()
    try:
        # 1. Verify m_gadgetworld and m_urbanrun exist in loaded data
        merchants = _load_merchants()
        assert "m_urbanrun" in merchants
        assert "m_gadgetworld" in merchants

        # Verify products exist and have correct merchant mappings
        products = _load_products()
        assert "ur_audio_001" in products
        assert products["ur_audio_001"].merchant_id == "m_urbanrun"
        assert "ur_comp_001" in products
        assert products["ur_comp_001"].merchant_id == "m_gadgetworld"

        # 2. Test create_cart validation
        # Valid merchant
        cart1 = cart_service.create_cart(merchant_id="m_urbanrun", customer_id="cust_test_01", db=db_session)
        assert cart1.merchant_id == "m_urbanrun"

        # Invalid merchant supplied
        with pytest.raises(ValueError, match="Merchant not found"):
            cart_service.create_cart(merchant_id="m_nonexistent", customer_id="cust_test_01", db=db_session)

        # 3. Test merchant mismatch on item addition
        # Add product matching cart merchant (m_urbanrun)
        cart_service.add_item_to_cart(cart_id=cart1.id, product_id="ur_audio_001", quantity=1, db=db_session)

        # Attempt to add product from different merchant (m_gadgetworld) to cart1
        with pytest.raises(cart_service.MerchantMismatchError, match="belongs to a different merchant"):
            cart_service.add_item_to_cart(cart_id=cart1.id, product_id="ur_comp_001", quantity=1, db=db_session)
    finally:
        db_session.close()
