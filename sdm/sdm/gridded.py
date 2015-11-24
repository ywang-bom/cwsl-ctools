"""
Extract data from gridded dataset, i.e. AWAP daily dataset

y.wang@bom.gov.au
"""
import os
import logging
from collections import namedtuple

import numpy as np
from scipy.io import netcdf

from .cod import CoD

logger = logging.getLogger('gridded')

Data2DBase = namedtuple('Data2DBase', 'data, dates, gpnames')
Data3DBase = namedtuple('Data3DBase', 'data, dates, lat, lon')


class Data2D(Data2DBase):

    def to_3d(self, mask):
        """

        :param mask:
        :type mask: mask.Mask
        """
        data = np.empty((self.data.shape[0], mask.data.size))
        data[:] = np.NaN

        data[:, mask.idx_mask_flat] = self.data
        data = data.reshape((self.data.shape[0], mask.data.shape[0], mask.data.shape[1]))

        return Data3D(data, self.dates, mask.lat, mask.lon)


class Data3D(Data3DBase):

    def to_2d(self, mask):
        data = np.empty((self.data.shape[0], len(mask.idx_mask_flat)))
        data[:] = np.NaN
        data = self.data.reshape((self.data.shape[0], self.data.shape[1] * self.data.shape[2]))[:, mask.idx_mask_flat]

        return Data2D(data, self.dates, mask.gpnames)

    def save_nc(self, filename, main_parameters):
        import datetime

        dates = (np.array([np.datetime64(d) for d in CoD.format_dates(self.dates)])
                 - np.datetime64('1899-12-31')).astype('int')

        f = netcdf.netcdf_file(filename, 'w')
        try:
            f.title = 'Daily gridded climate series (%s, %s, %s, %s, %s)' % (
                main_parameters.model, main_parameters.scenario,
                main_parameters.region_type, main_parameters.season,
                main_parameters.predictand)
            f.institution = 'Bureau of Meteorology'
            f.source = 'Statistical Downscaling Model'
            f.history = 'Generated on %s' % datetime.date.today()

            f.createDimension('time', 0)
            var_time = f.createVariable('time', np.float32, ('time',))
            var_time[:] = dates
            var_time.units = 'days since 1899-12-31 00:00:00'
            var_time.calendar = 'standard'

            f.createDimension('lat', self.lat.size)
            var_lat = f.createVariable('lat', float, ('lat',))
            var_lat[:] = self.lat
            var_lat.units = 'degrees_north'
            var_lat.long_name = 'latitude'
            var_lat.standard_name = 'latitude'

            f.createDimension('lon', self.lon.size)
            var_lon = f.createVariable('lon', float, ('lon',))
            var_lon[:] = self.lon
            var_lon.units = 'degrees_east'
            var_lon.long_name = 'longitude'
            var_lon.standard_name = 'longitude'

            predictand = main_parameters.get_var_code()
            missing_value = 99999.9
            var_data = f.createVariable(predictand, np.float32, ('time', 'lat', 'lon'))
            data = self.data.copy()
            data[np.where(np.isnan(data))] = missing_value
            var_data[:, :, :] = data
            var_data.units = 'mm' if predictand == 'rain' else 'K'
            var_data.long_name = main_parameters.predictand
            var_data.missing_value = var_data._FillValue = missing_value

        finally:
            f.close()


class DownscaledData2DReader(object):

    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.getcwd()

    def read(self, main_parameters):
        """

        :param main_parameters:
        :type main_parameters: parameters.MainParameters
        :return:
        :rtype:
        """
        file_path = os.path.join(self.base_dir, main_parameters.get_ds_file())
        logger.info('Reading {}'.format(file_path))

        ncd_file = netcdf.netcdf_file(file_path)
        var = ncd_file.variables[main_parameters.get_var_code()]
        data = var.data.copy()

        dates = ncd_file.variables['dates'].data.copy()
        gpnames = ncd_file.variables['gpnames'].data.copy()

        ncd_file.close()

        return Data2D(data, dates, gpnames)


class AwapDailyDataReader(object):

    def __init__(self, base_dir=None, verbose=False):
        self.resolution = '0.05'
        self.lat = np.arange(-4450, -995, 5) / 100.0
        self.lon = np.arange(11200, 15630, 5) / 100.0
        self.base_dir = base_dir or os.getcwd()
        self.verbose = verbose

    def read_one_file(self, var_name, year, month):
        if var_name in ['rr', 'rain']:
            var_code = 'rr'
            file_code = var_code + '_calib'
        else:
            var_code = var_name
            file_code = var_code

        file_path = os.path.join(self.base_dir,
                                 'daily_%s' % self.resolution,
                                 file_code,
                                 '%s_daily_%s.%04d%02d.nc' % (file_code, self.resolution, year, month))

        if self.verbose:
            print 'reading netcdf file: %s' % file_path
        ncd_file = netcdf.netcdf_file(file_path)
        var = ncd_file.variables[var_code]
        data = var.data.copy()
        data[np.where(var.data == var.missing_value)] = np.NaN
        ncd_file.close()

        return data

    def read_as_2d(self, var_name, adates, mask):

        date_components = CoD.calc_dates(adates)

        ret = np.empty((adates.size, mask.idx_mask_flat.size))
        ret[:] = np.NaN

        for yyyymm in sorted(set(date_components['yyyymm'])):
            data = self.read_one_file(var_name, yyyymm / 100, yyyymm % 100)
            data = data.reshape(data.shape[0], data.shape[1] * data.shape[2])

            idx_yyyymms = np.where(date_components['yyyymm'] == yyyymm)[0]
            idx_days = date_components['dd'][idx_yyyymms] - 1

            ret[idx_yyyymms, :] = data[idx_days, :][:, mask.idx_mask_flat]

        return Data2D(ret, adates, mask.gpnames)




