from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (QgsProcessing,
                       QgsProcessingAlgorithm,
                       QgsProcessingMultiStepFeedback,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterEnum,
                       QgsProperty,
                       QgsProcessingParameterBoolean,
                       QgsProcessingUtils)
import processing
from .utils import get_postgres_connections


class Exportar_elemento_associado_de_eletricidade(QgsProcessingAlgorithm):

    # Constants used to refer to parameters and outputs. They will be
    # used when calling the algorithm from another algorithm, or when
    # calling from the QGIS console.

    INPUT = 'INPUT'
    VALOR_ELEMENTO_ASSOCIADO_ELECTRICIDADE = 'VALOR_ELEMENTO_ASSOCIADO_ELECTRICIDADE'
    POSTGRES_CONNECTION = 'POSTGRES_CONNECTION'


    def initAlgorithm(self, config=None):
        self.postgres_connections_list = get_postgres_connections()

        self.addParameter(
            QgsProcessingParameterEnum(
                self.POSTGRES_CONNECTION,
                self.tr('Ligação PostgreSQL'),
                self.postgres_connections_list,
                defaultValue = 0
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr('Input point or polygon layer (2D)'),
                types=[QgsProcessing.TypeVectorPoint,QgsProcessing.TypeVectorPolygon],
                defaultValue=None
            )
        )

        self.valor_elemento_associado_eletricidade_dict = {
            'Central elétrica':'1.1',
            'Central fotovoltaica':'1.2',
            'Central eólica':'1.3',
            'Central termoelétrica':'1.4',
            'Subestação':'2',
            'Aeromotor':'3',
            'Gerador eólico':'4',
            'Painel solar fotovoltaico':'5',
            'Poste de iluminação':'6',
            'Poste de alta tensão':'7.1',
            'Poste de média tensão':'7.2',
            'Poste de baixa tensão':'7.3',
            'Torre de alta tensão':'7.4',
            'Posto transformador':'8'
        }

        self.addParameter(
            QgsProcessingParameterEnum(
                self.VALOR_ELEMENTO_ASSOCIADO_ELECTRICIDADE,
                self.tr('valorElementoAssociadoElectricidade'),
                list(self.valor_elemento_associado_eletricidade_dict.keys()),
                defaultValue=0,
                optional=False,
            )
        )

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(3, model_feedback)
        results = {}
        outputs = {}

        # Convert enumerator to final value
        enum = self.parameterAsEnum(
            parameters,
            self.VALOR_ELEMENTO_ASSOCIADO_ELECTRICIDADE,
            context
            )

        valor_associado_eletricidade = list(self.valor_elemento_associado_eletricidade_dict.values())[enum]

        # Refactor fields
        alg_params = {
            'FIELDS_MAPPING': [{
                'expression': 'now()',
                'length': -1,
                'name': 'inicio_objeto',
                'precision': -1,
                'type': 14
            },{
                'expression': str(valor_associado_eletricidade),
                'length': 255,
                'name': 'valor_elemento_associado_electricidade',
                'precision': -1,
                'type': 10
            }],
            'INPUT': parameters['INPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['RefactorFields'] = processing.run('qgis:refactorfields', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Sanitize Z and M values from 3D Layers
        # Input table only accepts 2D
        alg_params = {
            'DROP_M_VALUES': True,
            'DROP_Z_VALUES': True,
            'INPUT': outputs['RefactorFields']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['DropMzValues'] = processing.run('native:dropmzvalues', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Export to PostgreSQL (available connections)
        idx = self.parameterAsEnum(
            parameters,
            self.POSTGRES_CONNECTION,
            context
            )

        postgres_connection = self.postgres_connections_list[idx]

        # Because the target layer is of the geometry type, one needs to make
        # sure to use the correct option when importing into PostGIS
        layer = QgsProcessingUtils.mapLayerFromString(outputs['DropMzValues']['OUTPUT'], context)
        if layer.geometryType() == 0:
            gtype = 3
        elif layer.geometryType() == 2:
            gtype = 5

        alg_params = {
            'ADDFIELDS': True,
            'APPEND': True,
            'A_SRS': None,
            'CLIP': False,
            'DATABASE': postgres_connection,
            'DIM': 0,
            'GEOCOLUMN': 'geometria',
            'GT': '',
            'GTYPE': gtype,
            'INDEX': True,
            'INPUT': outputs['RefactorFields']['OUTPUT'],
            'LAUNDER': True,
            'OPTIONS': '',
            'OVERWRITE': False,
            'PK': '',
            'PRECISION': True,
            'PRIMARY_KEY': 'identificador',
            'PROMOTETOMULTI': True,
            'SCHEMA': 'public',
            'SEGMENTIZE': '',
            'SHAPE_ENCODING': '',
            'SIMPLIFY': '',
            'SKIPFAILURES': False,
            'SPAT': None,
            'S_SRS': None,
            'TABLE': 'elem_assoc_eletricidade',
            'T_SRS': None,
            'WHERE': ''
        }
        outputs['ExportToPostgresqlAvailableConnections'] = processing.run('gdal:importvectorintopostgisdatabaseavailableconnections', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        return results

    def name(self):
        return 'exportar_elemento_associado_de_eletricidade'

    def displayName(self):
        return '05. Exportar elemento associado de eletricidade'

    def group(self):
        return '08 - Infraestruturas e serviços'

    def groupId(self):
        return '08infraestruturas'

    def createInstance(self):
        return Exportar_elemento_associado_de_eletricidade()

    def tr(self, string):
        """
        Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def shortHelpString(self):
        return self.tr("Exporta elementos do tipo elemento associado de eletricidade para a base " \
                       "de dados RECART usando uma ligação PostgreSQL/PostGIS " \
                       "já configurada.\n\n" \
                       "A camada vectorial de input deve ser do tipo ponto ou polígono 2D ."
        )