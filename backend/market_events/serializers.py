from rest_framework import serializers
from .models import MarketEvent, MarketEventParticipation
from prospects.models import Prospect

class ParticipatingCompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Prospect
        fields = [
            'id', 'company_name', 'country_head_office', 'company_structure', 
            'operational_status', 'primary_industries'
        ]


class MarketEventSerializer(serializers.ModelSerializer):
    participating_companies_count = serializers.IntegerField(read_only=True)
    participating_companies = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = MarketEvent
        fields = [
            'id', 'event_title', 'host_country', 'start_date', 'end_date', 
            'website_url', 'participating_companies_count', 'participating_companies',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_participating_companies(self, obj):
        # We only want to serialize participating_companies for the Detail API.
        # DRF ViewSets usually pass `context['view'].action`. 
        # If action == 'list', we skip fetching to avoid N+1 and large payloads.
        request = self.context.get('request')
        if request and hasattr(request, 'parser_context'):
            view = request.parser_context.get('view')
            if view and view.action == 'list':
                return None
        
        if hasattr(obj, 'prefetched_participations'):
            prospects = [p.prospect for p in obj.prefetched_participations]
        else:
            prospects = Prospect.objects.filter(market_event_participations__market_event=obj)
            
            if request and request.user:
                user = request.user
                if not user.is_superuser and hasattr(user, 'profile'):
                    role = user.profile.role
                    if role in ('PRE', 'LQ'):
                        prospects = prospects.filter(created_by=user.username)

        return ParticipatingCompanySerializer(prospects, many=True).data

class MarketEventSimpleSerializer(serializers.ModelSerializer):
    """ Used when nesting Market Events inside Prospect serializer """
    class Meta:
        model = MarketEvent
        fields = ['id', 'event_title', 'host_country', 'start_date', 'end_date', 'website_url']
