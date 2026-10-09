import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from accounts.models import UserProfile

class Command(BaseCommand):
    help = 'Creates demo users for PRE and LQ roles'

    def handle(self, *args, **kwargs):
        from django.conf import settings
        if not settings.DEBUG:
            self.stdout.write(self.style.ERROR('This command can only be run in development (DEBUG=True).'))
            return
            
        pre_user, created = User.objects.get_or_create(username='pre_demo', defaults={'email': 'pre@example.com', 'first_name': 'PRE', 'last_name': 'Demo'})
        if created:
            pre_user.set_password('demo123')
            pre_user.save()
        else:
            UserProfile.objects.get_or_create(user=pre_user)
            
        pre_profile = pre_user.profile
        pre_profile.role = 'PRE'
        pre_profile.save()
        
        lq_user, created = User.objects.get_or_create(username='lq_demo', defaults={'email': 'lq@example.com', 'first_name': 'LQ', 'last_name': 'Demo'})
        if created:
            lq_user.set_password('demo123')
            lq_user.save()
        else:
            UserProfile.objects.get_or_create(user=lq_user)

        lq_profile = lq_user.profile
        lq_profile.role = 'LQ'
        lq_profile.save()
        
        self.stdout.write(self.style.SUCCESS('Successfully created PRE (pre_demo/demo123) and LQ (lq_demo/demo123) demo users.'))
