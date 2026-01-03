import os
import midtransclient
from flask import current_app

class PaymentService:
    def __init__(self):
        self.snap = midtransclient.Snap(
            is_production=os.environ.get('MIDTRANS_IS_PRODUCTION') == 'True',
            server_key=os.environ.get('MIDTRANS_SERVER_KEY')
        )

    def create_transaction(self, order_id, amount, customer_details=None):
        """
        Meminta Link Pembayaran ke Midtrans (Snap)
        """
        param = {
            "transaction_details": {
                "order_id": order_id,
                "gross_amount": amount
            },
            "credit_card": {
                "secure": True
            },
            # Data user biar otomatis terisi di layar pembayaran
            "customer_details": customer_details or {}
        }

        try:
            # Minta Snap Token & URL
            transaction = self.snap.create_transaction(param)
            return transaction # Isinya: {'token': '...', 'redirect_url': '...'}
        except Exception as e:
            print(f"Midtrans Error: {e}")
            return None

payment_service = PaymentService()