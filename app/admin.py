# from flask_admin import Admin, AdminIndexView, expose
# from flask_admin.contrib.sqla import ModelView
# from flask_login import current_user
# from flask import redirect, url_for
# from app.extensions import db
# from app.models.user import User
# from app.models.article import Article
# from app.models.withdrawal import Withdrawal
# from app.models.consultation import Consultation
# from app.models.medical import MedicalRecord

# # 1. Amankan Dashboard (Cuma Admin yang boleh masuk)
# class SecureModelView(ModelView):
#     def is_accessible(self):
#         return current_user.is_authenticated and current_user.role == 'ADMIN'

#     def inaccessible_callback(self, name, **kwargs):
#         return redirect(url_for('web.login_page'))

# # 2. Custom Tampilan untuk User
# class UserAdminView(SecureModelView):
#     column_list = ('full_name', 'email', 'role', 'is_verified', 'is_online', 'balance')
#     column_searchable_list = ('full_name', 'email')
#     column_filters = ('role', 'is_verified')
#     form_columns = ('full_name', 'email', 'password_hash', 'role', 'is_verified', 'specialization', 'consultation_price', 'balance')

# class WithdrawalAdminView(SecureModelView):
#     can_create = False
#     column_list = ('doctor', 'amount', 'bank_name', 'account_number', 'status', 'created_at')
#     form_columns = ('status',)

# class MyAdminIndexView(AdminIndexView):
#     @expose('/')
#     def index(self):
#         if not current_user.is_authenticated or current_user.role != 'ADMIN':
#             return redirect(url_for('web.login_page'))
#         return super(MyAdminIndexView, self).index()

# # 3. Setup Flask-Admin
# def setup_admin(app):
#     admin = Admin(app, name='Anemia App Admin', index_view=MyAdminIndexView())
    
#     admin.add_view(UserAdminView(User, db.session, name='Users'))
#     admin.add_view(SecureModelView(Article, db.session, name='Artikel'))
#     admin.add_view(WithdrawalAdminView(Withdrawal, db.session, name='Keuangan'))
#     admin.add_view(SecureModelView(Consultation, db.session, name='Konsultasi'))
#     admin.add_view(SecureModelView(MedicalRecord, db.session, name='Rekam Medis'))