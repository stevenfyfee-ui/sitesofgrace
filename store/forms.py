from django import forms


class WaitlistSignupForm(forms.Form):
    email = forms.EmailField()
    product_id = forms.IntegerField()
