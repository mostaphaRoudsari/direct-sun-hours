from pollination_dsl.dag import Inputs, DAG, task, Outputs
from dataclasses import dataclass
from pollination.honeybee_radiance.sun import CreateSunMatrix, ParseSunUpHours
from pollination.honeybee_radiance.translate import CreateRadianceFolder
from pollination.honeybee_radiance.octree import CreateOctreeWithSky


# input/output alias
from pollination.alias.inputs.model import hbjson_model_input
from pollination.alias.inputs.wea import wea_input
from pollination.alias.inputs.north import north_input
# from pollination.alias.outputs.daylight import sort_direct_results/direct_sun_hours

from ._raytracing import DirectSunHoursEntryLoop


@dataclass
class DirectSunHoursEntryPoint(DAG):
    """Direct sun hours entry point."""

    # inputs
    north = Inputs.float(
        default=0,
        description='A number for rotation from north.',
        spec={'type': 'number', 'minimum': 0, 'maximum': 360},
        alias=north_input
    )

    sensor_count = Inputs.int(
        default=200,
        description='The maximum number of grid points per parallel execution.',
        spec={'type': 'integer', 'minimum': 1}
    )

    sensor_grid = Inputs.str(
        description='A grid name or a pattern to filter the sensor grids. By default '
        'all the grids in HBJSON model will be exported.', default='*'
    )

    model = Inputs.file(
        description='A Honeybee model in HBJSON file format.',
        extensions=['json', 'hbjson'],
        alias=hbjson_model_input
    )

    wea = Inputs.file(
        description='Wea file.',
        extensions=['wea'],
        alias=wea_input
    )

    @task(template=CreateSunMatrix)
    def generate_sunpath(self, north=north, wea=wea, output_type=1):
        """Create sunpath for sun-up-hours."""
        return [
            {'from': CreateSunMatrix()._outputs.sunpath, 'to': 'resources/sunpath.mtx'},
            {
                'from': CreateSunMatrix()._outputs.sun_modifiers,
                'to': 'resources/suns.mod'
            }
        ]

    @task(template=CreateRadianceFolder)
    def create_rad_folder(self, input_model=model, sensor_grid=sensor_grid):
        """Translate the input model to a radiance folder."""
        return [
            {'from': CreateRadianceFolder()._outputs.model_folder, 'to': 'model'},
            {
                'from': CreateRadianceFolder()._outputs.sensor_grids_file,
                'to': 'results/direct_sun_hours/grids_info.json'
            },
            {
                'from': CreateRadianceFolder()._outputs.sensor_grids_file,
                'to': 'results/cumulative/grids_info.json'
            },
            {
                'from': CreateRadianceFolder()._outputs.sensor_grids_file,
                'to': 'results/direct_radiation/grids_info.json'
            },
            {
                'from': CreateRadianceFolder()._outputs.sensor_grids,
                'description': 'Sensor grids information.'
            }
        ]

    @task(
        template=CreateOctreeWithSky, needs=[generate_sunpath, create_rad_folder]
    )
    def create_octree(
        self, model=create_rad_folder._outputs.model_folder,
        sky=generate_sunpath._outputs.sunpath
    ):
        """Create octree from radiance folder and sunpath for direct studies."""
        return [
            {
                'from': CreateOctreeWithSky()._outputs.scene_file,
                'to': 'resources/scene_with_suns.oct'
            }
        ]

    @task(template=ParseSunUpHours, needs=[generate_sunpath])
    def parse_sun_up_hours(self, sun_modifiers=generate_sunpath._outputs.sun_modifiers):
        return [
            {
                'from': ParseSunUpHours()._outputs.sun_up_hours,
                'to': 'results/direct_sun_hours/sun-up-hours.txt'
            }
        ]

    @task(
        template=DirectSunHoursEntryLoop,
        needs=[create_octree, generate_sunpath, create_rad_folder],
        loop=create_rad_folder._outputs.sensor_grids,
        sub_folder='initial_results/{{item.name}}',  # create a subfolder for each grid
        sub_paths={'sensor_grid': 'grid/{{item.full_id}}.pts'}  # sub_path for sensor_grid arg
    )
    def direct_sun_hours_raytracing(
        self,
        sensor_count=sensor_count,
        octree_file=create_octree._outputs.scene_file,
        grid_name='{{item.full_id}}',
        sensor_grid=create_rad_folder._outputs.model_folder,
        sunpath=generate_sunpath._outputs.sunpath,
        sun_modifiers=generate_sunpath._outputs.sun_modifiers
    ):
        pass

    results = Outputs.folder(
        source='results',
        description='Results folder. There are 3 subfolders under results folder: '
        'direct_sun_hours, cumulative and direct_radiation.'
    )

    direct_sun_hours = Outputs.folder(
        source='results/direct_sun_hours',
        description='Hourly results for direct sun hours.',
        # alias=sort_direct_results/direct_sun_hours
    )

    cumulative_sun_hours = Outputs.folder(
        source='results/cumulative',
        description='Cumulative results for direct sun hours for all the input hours.',
        # alias=sort_direct_results/direct_sun_hours
    )

    direct_radiation = Outputs.folder(
        source='results/direct_radiation',
        description='Hourly direct radiation results. These results only includes the '
        'direct radiation from sun disk.',
        # alias=sort_direct_results/direct_sun_hours
    )
